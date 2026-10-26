//! 麦克风采集：cpal 默认输入设备 → 原生采样率单声道 i16 有界队列。
//! cpal 在 Windows 上的 Stream 含原生句柄、不是 Send，因此流始终驻留在
//! 专属采集线程内，对外只暴露 Send 安全的 `MicrophoneHandle`；
//! 句柄 drop（或会话结束）时通知线程退出并停止采集。

use super::resample;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use std::collections::VecDeque;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc, Arc, Mutex};

/// 采集线程与识别任务之间的音频队列；满则丢最旧，不阻塞音频线程。
pub struct AudioQueue {
    samples: Mutex<VecDeque<i16>>,
    cap: usize,
}

impl AudioQueue {
    fn new(cap: usize) -> Self {
        AudioQueue {
            samples: Mutex::new(VecDeque::with_capacity(cap)),
            cap,
        }
    }

    fn push(&self, chunk: &[i16]) {
        if chunk.is_empty() || self.cap == 0 {
            return;
        }
        // A single unusually large callback must not grow the queue past its cap.
        // Keep the newest samples because they are the most useful for live ASR.
        let chunk = if chunk.len() > self.cap {
            &chunk[chunk.len() - self.cap..]
        } else {
            chunk
        };
        let mut queue = match self.samples.lock() {
            Ok(queue) => queue,
            Err(poisoned) => poisoned.into_inner(),
        };
        let overflow = queue
            .len()
            .saturating_add(chunk.len())
            .saturating_sub(self.cap);
        if overflow > 0 {
            let drain = overflow.min(queue.len());
            queue.drain(..drain);
        }
        queue.extend(chunk.iter().copied());
    }

    pub fn drain(&self) -> Vec<i16> {
        let mut queue = match self.samples.lock() {
            Ok(queue) => queue,
            Err(poisoned) => poisoned.into_inner(),
        };
        queue.drain(..).collect()
    }
}

struct Started {
    queue: Arc<AudioQueue>,
    native_rate: u32,
    limit_reached: Arc<AtomicBool>,
    capture_failed: Arc<AtomicBool>,
}

/// Send 安全的采集句柄；drop 时停止采集线程。
pub struct MicrophoneHandle {
    pub queue: Arc<AudioQueue>,
    pub native_rate: u32,
    /// 录满上限后置位，由会话任务转为自动收尾。
    pub limit_reached: Arc<AtomicBool>,
    /// 设备断开或系统采集流报错后置位，避免前端一直等到会话总超时。
    pub capture_failed: Arc<AtomicBool>,
    stop: mpsc::Sender<()>,
}

impl Drop for MicrophoneHandle {
    fn drop(&mut self) {
        let _ = self.stop.send(());
    }
}

pub fn start_microphone(limit_seconds: u64) -> Result<MicrophoneHandle, String> {
    let (started_tx, started_rx) = mpsc::channel::<Result<Started, String>>();
    let (stop_tx, stop_rx) = mpsc::channel::<()>();
    std::thread::Builder::new()
        .name("voice-input-capture".into())
        .spawn(move || {
            let outcome = run_capture(limit_seconds);
            match outcome {
                Ok((stream, started)) => {
                    if started_tx.send(Ok(started)).is_err() {
                        return;
                    }
                    // 流驻留本线程；收到停止信号（或发送端 drop）后退出并停止采集。
                    let _ = stop_rx.recv();
                    drop(stream);
                }
                Err(error) => {
                    let _ = started_tx.send(Err(error));
                }
            }
        })
        .map_err(|_| "无法启动麦克风采集线程".to_string())?;
    match started_rx.recv() {
        Ok(Ok(started)) => Ok(MicrophoneHandle {
            queue: started.queue,
            native_rate: started.native_rate,
            limit_reached: started.limit_reached,
            capture_failed: started.capture_failed,
            stop: stop_tx,
        }),
        Ok(Err(error)) => Err(error),
        Err(_) => Err("麦克风采集线程意外退出".to_string()),
    }
}

fn recording_limit_samples(seconds: u64, sample_rate: u32) -> usize {
    seconds
        .saturating_mul(sample_rate as u64)
        .min(usize::MAX as u64) as usize
}

fn run_capture(limit_seconds: u64) -> Result<(cpal::Stream, Started), String> {
    let host = cpal::default_host();
    let device = host
        .default_input_device()
        .ok_or_else(|| "未找到可用的麦克风设备".to_string())?;
    let config = device
        .default_input_config()
        .map_err(|_| "无法读取麦克风配置，请检查系统隐私设置".to_string())?;
    let sample_rate = config.sample_rate().0;
    let channels = config.channels() as usize;
    if channels == 0 || sample_rate == 0 {
        return Err("麦克风返回了无效的采样配置".to_string());
    }
    let limit_samples = recording_limit_samples(limit_seconds, sample_rate);
    // 连接语音服务最长等待 10 秒；保留 15 秒输入即可覆盖连接抖动，
    // 总录音时长由独立计数器限制，避免队列按 60 秒原始采样率无限放大。
    let queue = Arc::new(AudioQueue::new((sample_rate as usize).saturating_mul(15)));
    let limit_reached = Arc::new(AtomicBool::new(false));
    let capture_failed = Arc::new(AtomicBool::new(false));
    let total = Arc::new(AtomicU64::new(0));

    fn wrap(
        queue: &Arc<AudioQueue>,
        total: &Arc<AtomicU64>,
        limit: &Arc<AtomicBool>,
        limit_samples: usize,
        mono: Vec<i16>,
    ) {
        let count = mono.len() as u64;
        queue.push(&mono);
        if total.fetch_add(count, Ordering::Relaxed) + count >= limit_samples as u64 {
            limit.store(true, Ordering::Relaxed);
        }
    }

    let stream = match config.sample_format() {
        cpal::SampleFormat::F32 => {
            let queue = queue.clone();
            let total = total.clone();
            let limit = limit_reached.clone();
            let failed = capture_failed.clone();
            device
                .build_input_stream(
                    &config.into(),
                    move |data: &[f32], _| {
                        let mono = mix_f32(data, channels);
                        wrap(&queue, &total, &limit, limit_samples, mono);
                    },
                    move |error| {
                        failed.store(true, Ordering::Relaxed);
                        eprintln!("voice input capture error: {error}");
                    },
                    None,
                )
                .map_err(|_| "麦克风无法启动，可能被其他程序占用".to_string())?
        }
        cpal::SampleFormat::I16 => {
            let queue = queue.clone();
            let total = total.clone();
            let limit = limit_reached.clone();
            let failed = capture_failed.clone();
            device
                .build_input_stream(
                    &config.into(),
                    move |data: &[i16], _| {
                        let mono = resample::mix_to_mono(data, channels);
                        wrap(&queue, &total, &limit, limit_samples, mono);
                    },
                    move |error| {
                        failed.store(true, Ordering::Relaxed);
                        eprintln!("voice input capture error: {error}");
                    },
                    None,
                )
                .map_err(|_| "麦克风无法启动，可能被其他程序占用".to_string())?
        }
        cpal::SampleFormat::U16 => {
            let queue = queue.clone();
            let total = total.clone();
            let limit = limit_reached.clone();
            let failed = capture_failed.clone();
            device
                .build_input_stream(
                    &config.into(),
                    move |data: &[u16], _| {
                        let mono: Vec<i16> = data
                            .chunks(channels)
                            .filter(|frame| frame.len() == channels)
                            .map(|frame| {
                                let sum: i64 = frame
                                    .iter()
                                    .map(|&s| (s as i16).wrapping_sub(i16::MIN) as i64)
                                    .sum();
                                let mean = sum / frame.len() as i64;
                                mean.clamp(i16::MIN as i64, i16::MAX as i64) as i16
                            })
                            .collect();
                        wrap(&queue, &total, &limit, limit_samples, mono);
                    },
                    move |error| {
                        failed.store(true, Ordering::Relaxed);
                        eprintln!("voice input capture error: {error}");
                    },
                    None,
                )
                .map_err(|_| "麦克风无法启动，可能被其他程序占用".to_string())?
        }
        other => return Err(format!("麦克风使用了暂不支持的采样格式：{other:?}")),
    };
    stream
        .play()
        .map_err(|_| "麦克风无法开始采集".to_string())?;

    Ok((
        stream,
        Started {
            queue,
            native_rate: sample_rate,
            limit_reached,
            capture_failed,
        },
    ))
}

fn mix_f32(data: &[f32], channels: usize) -> Vec<i16> {
    data.chunks(channels)
        .filter(|frame| frame.len() == channels)
        .map(|frame| {
            let sum: f32 = frame.iter().sum();
            let mean = sum / frame.len() as f32;
            (mean.clamp(-1.0, 1.0) * i16::MAX as f32) as i16
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::{recording_limit_samples, AudioQueue};

    #[test]
    fn audio_queue_keeps_only_the_newest_samples() {
        let queue = AudioQueue::new(5);
        queue.push(&[1, 2, 3]);
        queue.push(&[4, 5, 6]);
        assert_eq!(queue.drain(), vec![2, 3, 4, 5, 6]);

        let queue = AudioQueue::new(3);
        queue.push(&[1, 2, 3, 4, 5]);
        assert_eq!(queue.drain(), vec![3, 4, 5]);
    }

    #[test]
    fn recording_limit_uses_the_native_sample_rate() {
        assert_eq!(recording_limit_samples(60, 16_000), 960_000);
        assert_eq!(recording_limit_samples(60, 48_000), 2_880_000);
    }
}

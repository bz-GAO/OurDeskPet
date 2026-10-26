//! 麦克风原始采样 → ASR 需要的 16kHz 单声道 i16。
//! 一阶低通（抗混叠）+ 线性插值重采样，全部跨块保状态、纯逻辑可单测。

pub const TARGET_RATE: u32 = 16000;

/// 多声道交错 i16 → 单声道（平均）。
pub fn mix_to_mono(interleaved: &[i16], channels: usize) -> Vec<i16> {
    if channels <= 1 || interleaved.is_empty() {
        return interleaved.to_vec();
    }
    interleaved
        .chunks(channels)
        .filter(|frame| frame.len() == channels)
        .map(|frame| {
            let sum: i64 = frame.iter().map(|&sample| sample as i64).sum();
            let mean = sum / frame.len() as i64;
            mean.clamp(i16::MIN as i64, i16::MAX as i64) as i16
        })
        .collect()
}

/// 一阶低通，截止频率按目标采样率的奈奎斯特留裕量取 7kHz。
#[derive(Clone)]
struct LowPass {
    state: f32,
    alpha: f32,
}

impl LowPass {
    fn new(source_rate: u32) -> Self {
        let cutoff = 7000.0_f32;
        let alpha = 1.0 - (-std::f32::consts::TAU * cutoff / source_rate as f32).exp();
        LowPass { state: 0.0, alpha }
    }

    fn apply(&mut self, samples: impl Iterator<Item = f32>) -> Vec<f32> {
        samples
            .map(|x| {
                self.state += self.alpha * (x - self.state);
                self.state
            })
            .collect()
    }
}

/// 线性插值重采样到 16kHz。`pos` 是以输入样本为单位的绝对进度，
/// `tail` 保留上一块末尾的输入样本用于跨块插值。
#[derive(Clone)]
pub struct Resampler {
    step: f64,
    pos: f64,
    tail: Vec<f32>,
    low_pass: LowPass,
}

impl Resampler {
    pub fn new(source_rate: u32) -> Self {
        Resampler {
            step: source_rate as f64 / TARGET_RATE as f64,
            pos: 0.0,
            tail: Vec::new(),
            low_pass: LowPass::new(source_rate),
        }
    }

    pub fn process(&mut self, mono: &[i16]) -> Vec<i16> {
        if self.step <= 0.0 {
            return Vec::new();
        }
        let filtered = self.low_pass.apply(mono.iter().map(|&s| s as f32));
        let mut buffer: Vec<f32> = Vec::with_capacity(self.tail.len() + filtered.len());
        buffer.append(&mut self.tail);
        buffer.extend(filtered);
        let mut output = Vec::new();
        while (self.pos as usize) + 1 < buffer.len() {
            let index = self.pos as usize;
            let frac = (self.pos - index as f64) as f32;
            let value = buffer[index] + (buffer[index + 1] - buffer[index]) * frac;
            output.push(value.clamp(i16::MIN as f32, i16::MAX as f32) as i16);
            self.pos += self.step;
        }
        let consumed = self.pos as usize;
        self.tail = buffer[consumed.min(buffer.len())..].to_vec();
        self.pos -= consumed as f64;
        output
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mixes_stereo_to_mono_by_average() {
        assert_eq!(mix_to_mono(&[100, 200, -100, 300], 2), vec![150, 100]);
        assert_eq!(mix_to_mono(&[7, 8, 9], 1), vec![7, 8, 9]);
        assert_eq!(mix_to_mono(&[], 2), Vec::<i16>::new());
    }

    #[test]
    fn mono_passthrough_lags_one_sample_by_design() {
        let mut resampler = Resampler::new(TARGET_RATE);
        // 线性插值需要前瞻一个样本，流式实现把末样本留到下一块补出；
        // 首个样本带一阶低通的启动瞬态，收敛后回到原电平。
        let first = resampler.process(&[1000, 1000, 1000, 1000]);
        assert_eq!(first.len(), 3);
        assert!(first
            .iter()
            .skip(1)
            .all(|&sample| (sample - 1000).abs() <= 20));
        assert_eq!(resampler.process(&[1000]).len(), 1);
        assert!((resampler.process(&[1000])[0] - 1000).abs() <= 20);
    }

    #[test]
    fn constant_signal_converges_after_low_pass_warmup() {
        let mut resampler = Resampler::new(48000);
        let input = vec![1234_i16; 4800];
        let output = resampler.process(&input);
        assert!(output.len() > 1590, "output: {}", output.len());
        // 一阶低通有启动瞬态，收敛后的输出应回到原电平。
        let converged = &output[output.len().min(100)..];
        assert!(converged.iter().all(|&sample| (sample - 1234).abs() <= 2));
    }

    #[test]
    fn output_length_tracks_input_ratio_across_chunks() {
        let mut resampler = Resampler::new(48000);
        let chunk: Vec<i16> = (0..4800).map(|i| (i % 97) as i16).collect();
        let first = resampler.process(&chunk);
        let second = resampler.process(&chunk);
        // 48000 → 16000 精确 3:1，两块 100ms 输入应各产出约 1600 样本。
        assert!(
            (first.len() as i64 - 1600).abs() <= 3,
            "first: {}",
            first.len()
        );
        assert!(
            (second.len() as i64 - 1600).abs() <= 3,
            "second: {}",
            second.len()
        );
    }

    #[test]
    fn odd_ratio_44100_resamples_without_blowing_up() {
        let mut resampler = Resampler::new(44100);
        let chunk: Vec<i16> = (0..4410).map(|i| ((i % 211) * 30 - 3000) as i16).collect();
        let output = resampler.process(&chunk);
        assert!((output.len() as f64 - 1600.0).abs() <= 3.0);
        assert!(output.iter().all(|&s| s.abs() <= 4000));
    }

    #[test]
    fn low_pass_attenuates_high_frequency_relative_to_dc() {
        let mut dc = Resampler::new(48000);
        let mut hf = Resampler::new(48000);
        let steady: Vec<i16> = vec![10000; 3000];
        let alternating: Vec<i16> = (0..3000)
            .map(|i| if i % 2 == 0 { 10000 } else { -10000 })
            .collect();
        let dc_peak = dc.process(&steady).iter().map(|s| s.abs()).max().unwrap();
        let hf_peak = hf
            .process(&alternating)
            .iter()
            .map(|s| s.abs())
            .max()
            .unwrap();
        assert!(dc_peak > 9000, "dc: {dc_peak}");
        assert!(
            hf_peak < dc_peak,
            "hf should be attenuated: {hf_peak} vs {dc_peak}"
        );
    }
}

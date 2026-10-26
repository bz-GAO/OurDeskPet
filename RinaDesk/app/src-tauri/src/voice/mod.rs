//! Desk 语音功能。按"说话的方向"分为两侧，互不依赖：
//! `input` 是用户语音→文字；`output` 是桌宠事件音效与语音回复回放。
//! 见本目录 README.md 与仓库 docs/VOICE.md。
pub mod input;
pub mod output;
pub mod tts;

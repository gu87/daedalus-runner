//! Fetch a URL and return cleaned text content.
//!
//! Input: `{"url": "https://...", "max_bytes": 102400}`
//! Output: text content with HTML tags stripped.
//!
//! Safety: only http/https URLs, 30s timeout, size-limited.

use async_trait::async_trait;
use serde_json::{json, Value};

use crate::types::{RiskLevel, ToolDef, ToolResult};

use super::{map_validate_err, Tool, ToolContext, ToolError};

pub struct WebFetchTool;

fn strip_html(html: &str) -> String {
    let mut out = String::with_capacity(html.len());
    let mut in_tag = false;
    let mut in_script = false;
    let mut last_was_space = true;
    let mut chars = html.chars().peekable();

    while let Some(c) = chars.next() {
        if in_tag {
            if c == '>' {
                in_tag = false;
                // 检查是否是 script/style 结束
                if in_script {
                    // 简单处理：遇到 </ 就退出 script 模式由外层判断
                }
            }
            continue;
        }
        if c == '<' {
            // 检查 script/style 开始
            let rest: String = chars.clone().take(10).collect::<String>().to_lowercase();
            if rest.starts_with("script") || rest.starts_with("style") {
                in_script = true;
            } else if rest.starts_with("/script") || rest.starts_with("/style") {
                in_script = false;
            }
            in_tag = true;
            continue;
        }
        if in_script {
            continue;
        }
        if c.is_whitespace() {
            if !last_was_space {
                out.push(' ');
                last_was_space = true;
            }
        } else {
            out.push(c);
            last_was_space = false;
        }
    }
    out.trim().to_string()
}

#[async_trait]
impl Tool for WebFetchTool {
    fn definition(&self) -> ToolDef {
        ToolDef {
            name: "web_fetch".into(),
            description: "Fetch a URL and return cleaned text content (HTML stripped). For reading docs, APIs, web pages.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "http(s) URL to fetch"
                    },
                    "max_bytes": {
                        "type": "integer",
                        "description": "Max bytes of cleaned text (default 50000)"
                    }
                },
                "required": ["url"]
            }),
        }
    }

    fn risk_level(&self) -> RiskLevel {
        RiskLevel::R2
    }

    fn allowed_agents(&self) -> Vec<String> {
        vec!["*".into()]
    }

    fn needs_permission(&self, _args: &Value) -> bool {
        false
    }

    fn validate(&self, input: &Value, _ctx: &ToolContext) -> Result<(), String> {
        let url = input["url"]
            .as_str()
            .ok_or_else(|| "web_fetch: 'url' must be a string".to_string())?;
        if url.is_empty() {
            return Err("web_fetch: 'url' must not be empty".into());
        }
        if !url.starts_with("http://") && !url.starts_with("https://") {
            return Err("web_fetch: only http(s) URLs allowed".into());
        }
        Ok(())
    }

    async fn execute(&self, input: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        if let Err(e) = self.validate(&input, ctx) {
            return Err(map_validate_err(e));
        }
        let url = input["url"].as_str().unwrap();
        let max_bytes = input["max_bytes"].as_u64().unwrap_or(50000) as usize;

        // 用 curl（走系统代理，已验证可用），不用 reqwest（代理配置有坑）
        let output = tokio::process::Command::new("curl")
            .args(["-sL", "--max-time", "30", "-A", "daedalus-webfetch/0.1", url])
            .output()
            .await
            .map_err(|e| ToolError::Io(std::io::Error::new(std::io::ErrorKind::Other, format!("curl failed: {}", e))))?;

        if !output.status.success() {
            return Err(ToolError::InvalidInput(format!(
                "web_fetch: curl failed for {} (exit {})",
                url,
                output.status.code().unwrap_or(-1)
            )));
        }

        let html = String::from_utf8_lossy(&output.stdout);
        let text = strip_html(&html);
        let bytes = text.as_bytes();
        let output = if bytes.len() > max_bytes {
            format!(
                "{}\n... [truncated: {} bytes total]",
                String::from_utf8_lossy(&bytes[..max_bytes]),
                bytes.len()
            )
        } else {
            text
        };

        Ok(ToolResult {
            output,
            is_error: false,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strip_html_basic() {
        assert_eq!(strip_html("<p>hello <b>world</b></p>"), "hello world");
    }

    #[test]
    fn strip_html_script() {
        assert_eq!(
            strip_html("<script>alert(1)</script><p>text</p>"),
            "text"
        );
    }

    #[test]
    fn strip_html_whitespace() {
        assert_eq!(strip_html("<div>  a   b  </div>"), "a b");
    }

    #[test]
    fn validate_rejects_non_http() {
        let t = WebFetchTool;
        let ctx = ToolContext {
            agent_id: "test".into(),
            work_dir: std::path::PathBuf::from("/tmp"),
            must_keep: vec![],
            denied_commands: vec![],
        };
        assert!(t.validate(&json!({"url": "ftp://x.com"}), &ctx).is_err());
        assert!(t.validate(&json!({"url": "https://example.com"}), &ctx).is_ok());
    }
}

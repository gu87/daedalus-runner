//! Search the web via Tavily (agent-optimized search API).
//!
//! Input: `{"query": "...", "max_results": 5}`
//! Output: cleaned search results with titles, URLs, and snippets.

use async_trait::async_trait;
use serde_json::{json, Value};

use crate::types::{RiskLevel, ToolDef, ToolResult};

use super::{map_validate_err, Tool, ToolContext, ToolError};

pub struct WebSearchTool;

#[async_trait]
impl Tool for WebSearchTool {
    fn definition(&self) -> ToolDef {
        ToolDef {
            name: "web_search".into(),
            description: "Search the web for information. Returns titles, URLs, and content snippets. Use for research, docs lookup, current events.".into(),
            input_schema: json!({
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max results (default 5, max 10)"
                    }
                },
                "required": ["query"]
            }),
        }
    }

    fn risk_level(&self) -> RiskLevel {
        RiskLevel::R1
    }

    fn allowed_agents(&self) -> Vec<String> {
        vec!["*".into()]
    }

    fn needs_permission(&self, _args: &Value) -> bool {
        false
    }

    fn validate(&self, input: &Value, _ctx: &ToolContext) -> Result<(), String> {
        let q = input["query"]
            .as_str()
            .ok_or_else(|| "web_search: 'query' must be a string".to_string())?;
        if q.is_empty() {
            return Err("web_search: 'query' must not be empty".into());
        }
        Ok(())
    }

    async fn execute(&self, input: Value, ctx: &ToolContext) -> Result<ToolResult, ToolError> {
        if let Err(e) = self.validate(&input, ctx) {
            return Err(map_validate_err(e));
        }
        let query = input["query"].as_str().unwrap();
        let max_results = input["max_results"].as_u64().unwrap_or(5).min(10);

        // 走本地代理，由代理注入 Tavily 凭证
        let body = json!({
            "query": query,
            "max_results": max_results,
            "include_answer": true,
        });

        let output = tokio::process::Command::new("curl")
            .args([
                "-s", "--max-time", "30",
                "-X", "POST",
                "-H", "Content-Type: application/json",
                "-d", &body.to_string(),
                "http://127.0.0.1:8899/tavily/search",
            ])
            .output()
            .await
            .map_err(|e| ToolError::Io(std::io::Error::new(
                std::io::ErrorKind::Other,
                format!("curl failed: {}", e),
            )))?;

        if !output.status.success() {
            return Err(ToolError::InvalidInput(format!(
                "web_search: request failed (exit {})",
                output.status.code().unwrap_or(-1)
            )));
        }

        let resp: Value = serde_json::from_slice(&output.stdout).map_err(|e| {
            ToolError::InvalidInput(format!("web_search: bad response: {}", e))
        })?;

        // 整理成干净文本
        let mut out = String::new();
        if let Some(answer) = resp["answer"].as_str() {
            if !answer.is_empty() {
                out.push_str(&format!("【直接答案】{}\n\n", answer));
            }
        }
        if let Some(results) = resp["results"].as_array() {
            for (i, r) in results.iter().enumerate() {
                let title = r["title"].as_str().unwrap_or("(no title)");
                let url = r["url"].as_str().unwrap_or("");
                let content = r["content"].as_str().unwrap_or("");
                // 截断过长 content
                let snippet: String = content.chars().take(500).collect();
                out.push_str(&format!("{}. {}\n   {}\n   {}\n\n", i + 1, title, url, snippet));
            }
        }
        if out.is_empty() {
            out = "没有找到相关结果。".to_string();
        }

        Ok(ToolResult {
            output: out,
            is_error: false,
        })
    }
}

//! Browser harness using headless Chrome (CDP). Open URL, snapshot (DOM + screenshot), click, type.

use std::sync::Arc;

use headless_chrome::browser::{Browser, Tab};
use headless_chrome::protocol::cdp::Page::CaptureScreenshotFormatOption;

/// Result of getting a page snapshot (DOM excerpt + screenshot base64).
pub struct Snapshot {
    pub url: String,
    pub title: String,
    pub body_text: String,
    pub screenshot_base64: Option<String>,
}

/// Browser harness. Holds a browser and optionally a tab.
pub struct BrowserHarness {
    browser: Option<Browser>,
    tab: Option<Arc<Tab>>,
}

impl BrowserHarness {
    pub fn new() -> Self {
        BrowserHarness {
            browser: None,
            tab: None,
        }
    }

    /// Launch browser if not already.
    fn ensure_browser(&mut self) -> Result<(), String> {
        if self.browser.is_none() {
            let browser = Browser::default().map_err(|e| e.to_string())?;
            let tab = browser.new_tab().map_err(|e| e.to_string())?;
            self.tab = Some(tab);
            self.browser = Some(browser);
        }
        Ok(())
    }

    fn tab(&self) -> Result<Arc<Tab>, String> {
        self.tab
            .clone()
            .ok_or_else(|| "Browser not launched".to_string())
    }

    /// Open URL and wait for load.
    pub fn open_url(&mut self, url: &str) -> Result<(), String> {
        self.ensure_browser()?;
        let tab = self.tab()?;
        tab.navigate_to(url).map_err(|e| e.to_string())?;
        tab.wait_until_navigated().map_err(|e| e.to_string())?;
        Ok(())
    }

    /// Get current page snapshot: URL, title, body text, screenshot.
    pub fn get_snapshot(&self, include_screenshot: bool) -> Result<Snapshot, String> {
        let tab = self.tab()?;
        let url = tab.get_url();
        let title = tab
            .evaluate("document.title", true)
            .ok()
            .and_then(|ro| ro.value.as_ref().and_then(|v| v.as_str().map(String::from)))
            .unwrap_or_default();
        let body_text = tab
            .evaluate("document.body ? document.body.innerText.slice(0, 8000) : ''", true)
            .ok()
            .and_then(|ro| ro.value.as_ref().and_then(|v| v.as_str().map(String::from)))
            .unwrap_or_default();

        let screenshot_base64 = if include_screenshot {
            let bytes = tab
                .capture_screenshot(CaptureScreenshotFormatOption::Png, None, None, true)
                .map_err(|e| e.to_string())?;
            Some(base64::Engine::encode(
                &base64::engine::general_purpose::STANDARD,
                &bytes,
            ))
        } else {
            None
        };

        Ok(Snapshot {
            url,
            title,
            body_text,
            screenshot_base64,
        })
    }

    /// Click element by CSS selector.
    pub fn click(&self, selector: &str) -> Result<(), String> {
        let tab = self.tab()?;
        let el = tab.wait_for_element(selector).map_err(|e| e.to_string())?;
        el.click().map_err(|e| e.to_string())?;
        Ok(())
    }

    /// Type text into element (by selector). Clears existing value.
    pub fn type_into(&self, selector: &str, text: &str) -> Result<(), String> {
        let tab = self.tab()?;
        let el = tab.wait_for_element(selector).map_err(|e| e.to_string())?;
        el.type_into(text).map_err(|e| e.to_string())?;
        Ok(())
    }

    /// Close browser.
    pub fn close(&mut self) {
        self.tab = None;
        self.browser = None;
    }
}

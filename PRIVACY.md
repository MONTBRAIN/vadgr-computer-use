# Privacy Policy — vadgr-computer-use browser tier

_Last updated: 2026-07-22_

The **vadgr-computer-use browser tier** is a Chrome extension that acts as a
bridge between your browser and the **vadgr-computer-use** MCP server that you
install and run on your own machine. It only does something when that local
host sends it a command, and it exists solely to let an AI agent you connect
operate the pages you direct it to.

## What the extension handles

To perform the actions you ask of it, the extension can access:

- **Website content** — text, values, and elements of the page it is told to
  act on, so it can read the page, fill forms, click, and extract data.
- **Authentication information** — it exposes a scoped cookie read/write
  operation for the current site when a task requires it.
- **Web history** — the URLs and titles of your open tabs, so the agent can
  find and switch to the right page.

## How that data is used

- All of the above is **forwarded only to the vadgr-computer-use host running
  locally on your own device**, over Chrome's native messaging channel, so the
  host can carry out the action you requested.
- The extension **does not send your data to the developer**, and it does not
  transmit your data to any server operated by us.
- Data is handled **only to fulfill the extension's single purpose** (operating
  the browser on your behalf). It is never sold, and it is never used to
  determine creditworthiness or for lending.
- What your local host and the AI agent you connect to it (for example, Claude
  Code or a CLI agent) do with data afterward is governed by **your** choice of
  those tools and their own policies. You control which agent you connect and
  which pages it acts on.

## What the extension stores

- The extension stores a **single random identifier** for each browser profile
  (in `chrome.storage.local`) so the local host can tell multiple connected
  Chrome profiles apart.
- It does **not** store your browsing data, page content, or cookies.

## Your control

- The extension is inert unless the local vadgr-computer-use host is installed,
  registered, and running.
- Removing the extension, or stopping the local host, ends all access.

## Contact

Questions about this policy: **santiagoe4333@gmail.com**

Source code: https://github.com/MONTBRAIN/vadgr-computer-use

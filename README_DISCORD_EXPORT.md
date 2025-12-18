# GuildedChatExporter - Multiple Export Formats

Export Guilded servers in Discord takeout format or raw JSON before the platform shutdown.

## Important Notice

**Guilded.gg is shutting down on January 1, 2026.** This exporter helps you preserve your Guilded server data in multiple formats.

## Export Formats

### 1. Discord Takeout Format
Converts Guilded data to Discord-compatible format for potential Spacebar import.

**Features:**
- ✅ Exports to Discord takeout folder structure
- ✅ Full JSON message objects (not CSV)
- ✅ Downloads all attachments for preservation
- ✅ Converts Slate.js content to Discord markdown
- ✅ Maps channel types (media → GUILD_MEDIA, docs/lists → forums)
- ✅ Exports reactions (if available)
- ✅ Marks pinned messages
- ✅ Converts permissions to Discord bitmasks
- ✅ **Exports reply threads** (not forum threads) with full message history

### 2. Raw JSON Format (Recommended)
Saves raw Guilded API responses with complete message history using cursor rewinding.

**Features:**
- ✅ Preserves all Guilded-specific fields
- ✅ Complete message history via cursor-based pagination
- ✅ No data loss from conversion
- ✅ Suitable for custom importers
- ✅ All metadata preserved exactly as received from Guilded
- ✅ **Exports reply threads** (active and archived) with full message history

## Requirements

- Python 3.7+
- `requests` library
- `python-socketio` library (for raw export)
- `aiohttp` library (for raw export)
- Guilded account with access to the server you want to export

## Installation

```bash
# Clone the repository
git clone https://github.com/erkinalp/GuildedChatExporter.git
cd GuildedChatExporter

# Install dependencies
pip install requests python-socketio aiohttp
```

## Usage

### Interactive Mode (Recommended)

```bash
python3 export.py
```

Follow the prompts to:
1. Choose export format (Discord Takeout or Raw JSON)
2. Enter your Guilded authentication token
3. Select a server to export
4. Confirm and start the export

**Which format should I choose?**
- Choose **Discord Takeout** if you plan to import directly into Spacebar
- Choose **Raw JSON** to preserve all data and write a custom importer later (recommended by Spacebar developers)

### Getting Your Authentication Token

1. Open Guilded in your web browser (not the desktop app)
2. Press **F12** (Chrome) or **Shift+F9** (Firefox) to open Developer Tools
3. Go to the **Application** tab (Chrome) or **Storage** tab (Firefox)
4. Click on **Cookies** → **guilded.gg**
5. Find the `hmac_signed_session` cookie and copy its **Value**
6. Paste this value when prompted by the export script

⚠️ **Security**: Never share your token with anyone - it gives full access to your account!

### Programmatic Usage

**Discord Format:**
```python
from guilded_to_discord_exporter import GuildedToDiscordExporter

exporter = GuildedToDiscordExporter(
    auth_token="your-hmac-signed-session-token",
    output_dir="./my-export",
    export_format="discord"
)

exporter.export_all(
    server_id="your-server-id",
    server_name="Your Server Name"
)
```

**Raw JSON Format:**
```python
import asyncio
from guilded_websocket_exporter import GuildedWebSocketExporter

async def export():
    exporter = GuildedWebSocketExporter(
        auth_token="your-hmac-signed-session-token",
        output_dir="./my-export"
    )
    
    await exporter.export_server_full(
        server_id="your-server-id",
        server_name="Your Server Name"
    )

asyncio.run(export())
```

## Export Structure

### Discord Takeout Format

```
guilded-export/
├── README.txt
├── account/
│   ├── avatar.png
│   └── user.json
├── messages/
│   ├── index.json
│   └── c{channel_id}/
│       ├── channel.json
│       ├── messages.json
│       ├── attachments/
│       └── threads/              # Reply threads (if any)
│           └── {thread_id}/
│               ├── channel.json
│               └── messages.json
└── servers/{guild_id}/
    ├── guild.json
    └── audit-log.json
```

### Raw JSON Format

```
guilded-export/
└── raw_websocket/
    ├── README.txt
    ├── user.json
    ├── server_{server_id}_info.json
    ├── server_{server_id}_channels.json
    ├── server_{server_id}_members.json
    ├── server_{server_id}_groups.json
    ├── server_{server_id}_roles.json
    ├── channel_{channel_id}_messages.json
    ├── channel_{channel_id}_pinned.json
    └── channel_{channel_id}/           # Per-channel directory
        └── threads/                    # Reply threads (if any)
            ├── {channel_id}_threads_metadata.json
            └── {thread_id}/
                ├── {thread_id}_info.json
                └── {thread_id}_messages.json
```

## Channel Type Mappings

| Guilded Channel | Discord Type | Notes |
|-----------------|--------------|-------|
| chat | GUILD_TEXT (0) | Direct mapping |
| voice | GUILD_VOICE (2) | Direct mapping |
| stream | GUILD_STAGE_VOICE (13) | Mapped to stage channels |
| announcement | GUILD_ANNOUNCEMENT (5) | Direct mapping |
| forum | GUILD_FORUM (15) | Direct mapping |
| **media** | **GUILD_MEDIA (16)** | Direct mapping |
| **docs** | **GUILD_FORUM (15)** | Converted to forum with threads |
| **lists** | **GUILD_FORUM (15)** | Converted to forum with threads |
| scheduling | *(dropped)* | No Discord equivalent |

## Content Conversion

### Slate.js → Markdown

Guilded uses Slate.js for rich text. The exporter converts it to Discord markdown:

- **Bold**: `**text**`
- *Italic*: `*text*`
- Underline: `__text__`
- Strikethrough: `~~text~~`
- Code: `` `text` ``
- Links: `[text](url)`
- Mentions: `<@userid>`, `<@&roleid>`, `<#channelid>`
- Custom Emojis: `<:name:id>` or `<a:name:id>` (animated)

### Attachments

All attachments are downloaded to preserve data before Guilded shuts down. Files are saved in:
```
messages/c{channel_id}/attachments/
```

### Reactions

Reactions are exported if available via the Guilded API.

### Pinned Messages

The exporter fetches pinned messages and marks them with `"pinned": true` in the message objects.

## Permission Mapping

Guilded permissions are converted to Discord permission bitmasks:

| Guilded Permission | Discord Permission |
|--------------------|-------------------|
| CanUpdateTeam | MANAGE_GUILD |
| CanManageRoles | MANAGE_ROLES |
| CanManageChannels | MANAGE_CHANNELS |
| CanReadChats | VIEW_CHANNEL |
| CanCreateChats | SEND_MESSAGES |
| CanUploadChatMedia | ATTACH_FILES |
| CanListenVoice | CONNECT |
| CanAddVoice | SPEAK |
| ...and more | |

Guilded-specific permissions (docs, lists, scheduling, XP, etc.) are dropped as they have no Discord equivalent.

## Importing to Spacebar

**Important**: According to Spacebar developers, Spacebar does not currently have a built-in import feature. The recommended approach is:

1. Use the **Raw JSON format** to export your data
2. The raw export preserves all Guilded fields without data loss
3. Write a custom database importer for Spacebar using the raw JSON data
4. This approach allows maximum flexibility without time pressure

For Discord Takeout format:
- The export structure mimics Discord takeout format
- Can be used as reference for writing Spacebar importers
- Useful for documentation and archival purposes

**Note**: Spacebar supports non-snowflake IDs, so Guilded's UUIDs are preserved as-is.

## Troubleshooting

### "Error fetching data: 401"
- Your authentication token has expired or is invalid
- Get a new token from your browser's developer tools

### "Error fetching data: 403"
- You don't have permission to access that channel
- The exporter will skip channels you can't access

### "KeyboardInterrupt"
- You pressed Ctrl+C to cancel the export
- This is normal - the export was interrupted by user action

### Rate Limiting
- The exporter includes a 0.5-second delay between message page fetches
- For very large servers, the export may take a while

## Limitations

- **Audit logs**: Not available via Guilded API (empty file created)
- **Reactions**: May not be available for all messages via API
- **User data**: Only basic user info is exported (IDs, not full profiles)
- **Docs/Lists structure**: Currently flattened to forum threads (structure decision deferred)

## Contributing

This exporter was created to preserve Guilded data before the platform shuts down. Contributions welcome!

## License

This project maintains the same license as the original GuildedChatExporter.

## Credits

- Original HTML exporter: [Fatih120/GuildedChatExporter](https://github.com/Fatih120/GuildedChatExporter)
- Discord takeout format exporter: Created for Spacebar compatibility
- Developed by: Devin (erkinalp9035@gmail.com)

## Support

For issues or questions:
- Open an issue on GitHub
- Contact: erkinalp9035@gmail.com
- Devin session: https://app.devin.ai/sessions/0a84ee34504444cd81762939cf661fd6

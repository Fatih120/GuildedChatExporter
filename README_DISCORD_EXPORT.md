# GuildedChatExporter - Discord Takeout Format

Export Guilded servers to Discord takeout format for Spacebar import.

## Important Notice

**Guilded.gg is shutting down on January 1, 2026.** This exporter helps you preserve your Guilded server data in a format compatible with Spacebar.

## Features

- ✅ Exports to Discord takeout folder structure
- ✅ Full JSON message objects (not CSV)
- ✅ Downloads all attachments for preservation
- ✅ Converts Slate.js content to Discord markdown
- ✅ Maps channel types (media → GUILD_MEDIA, docs/lists → forums)
- ✅ Exports reactions (if available)
- ✅ Marks pinned messages
- ✅ Converts permissions to Discord bitmasks
- ✅ Ready for Spacebar import

## Requirements

- Python 3.7+
- `requests` library
- Guilded account with access to the server you want to export

## Installation

```bash
# Clone the repository
git clone https://github.com/erkinalp/GuildedChatExporter.git
cd GuildedChatExporter

# Install dependencies
pip install requests
```

## Usage

### Interactive Mode (Recommended)

```bash
python3 export.py
```

Follow the prompts to:
1. Enter your Guilded authentication token
2. Select a server to export
3. Confirm and start the export

### Getting Your Authentication Token

1. Open Guilded in your web browser (not the desktop app)
2. Press **F12** (Chrome) or **Shift+F9** (Firefox) to open Developer Tools
3. Go to the **Application** tab (Chrome) or **Storage** tab (Firefox)
4. Click on **Cookies** → **guilded.gg**
5. Find the `hmac_signed_session` cookie and copy its **Value**
6. Paste this value when prompted by the export script

⚠️ **Security**: Never share your token with anyone - it gives full access to your account!

### Programmatic Usage

```python
from guilded_to_discord_exporter import GuildedToDiscordExporter

# Initialize exporter
exporter = GuildedToDiscordExporter(
    auth_token="your-hmac-signed-session-token",
    output_dir="./my-export"
)

# Export a specific server
exporter.export_all(
    server_id="your-server-id",
    server_name="Your Server Name"
)
```

## Export Structure

The exporter creates a Discord-compatible folder structure:

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
│       └── attachments/
└── servers/{guild_id}/
    ├── guild.json
    └── audit-log.json
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

After exporting, you can import the data into Spacebar:

1. Locate your export directory (default: `./guilded-export`)
2. Follow Spacebar's import documentation
3. The export format matches Discord takeout structure

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

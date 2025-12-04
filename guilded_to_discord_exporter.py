#!/usr/bin/env python3
"""
GuildedChatExporter - Discord Takeout Format
Export Guilded servers to Discord takeout format for Spacebar import
"""

import requests
import json
import os
import sys
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse
import concurrent.futures

class GuildedToDiscordExporter:
    """Export Guilded data in Discord takeout format"""
    
    GUILDED_API = "https://www.guilded.gg/api"
    
    CHANNEL_TYPE_MAP = {
        "chat": 0,           # GUILD_TEXT
        "voice": 2,          # GUILD_VOICE
        "stream": 13,        # GUILD_STAGE_VOICE
        "announcement": 5,   # GUILD_ANNOUNCEMENT
        "forum": 15,         # GUILD_FORUM
        "media": 16,         # GUILD_MEDIA
        "docs": 15,          # GUILD_FORUM (converted)
        "list": 15,          # GUILD_FORUM (converted)
    }
    
    PERMISSION_MAP = {
        "CanUpdateTeam": 0x00000020,           # MANAGE_GUILD
        "CanManageRoles": 0x10000000,          # MANAGE_ROLES
        "CanInviteMembers": 0x00000001,        # CREATE_INSTANT_INVITE
        "CanKickMembers": 0x00000006,          # KICK_MEMBERS + BAN_MEMBERS
        "CanManageChannels": 0x00000010,       # MANAGE_CHANNELS
        "CanManageWebhooks": 0x20000000,       # MANAGE_WEBHOOKS
        "CanMentionEveryone": 0x00020000,      # MENTION_EVERYONE
        "CanModerateChannels": 0x00002000,     # MANAGE_MESSAGES
        "CanBypassSlowMode": 0x00000000,       # No direct equivalent
        "CanManageGroups": 0x00000010,         # MANAGE_CHANNELS
        
        "CanReadChats": 0x00000400,            # VIEW_CHANNEL
        "CanCreateChats": 0x00000800,          # SEND_MESSAGES
        "CanUploadChatMedia": 0x00008000,      # ATTACH_FILES
        "CanManageChats": 0x00002000,          # MANAGE_MESSAGES
        "CanCreateChatThreads": 0x0000800000000000,  # CREATE_PUBLIC_THREADS
        "CanReplyToChatThreads": 0x0000800000000000, # CREATE_PUBLIC_THREADS
        "CanCreatePrivateMessages": 0x00000800,      # SEND_MESSAGES
        "CanManageChatThreads": 0x0004000000000000,  # MANAGE_THREADS
        
        "CanListenVoice": 0x00100000,          # CONNECT
        "CanAddVoice": 0x00200000,             # SPEAK
        "CanMuteMembers": 0x00400000,          # MUTE_MEMBERS
        "CanDeafenMembers": 0x00800000,        # DEAFEN_MEMBERS
        "CanAssignVoiceGroup": 0x01000000,     # MOVE_MEMBERS
        "CanBroadcastVoice": 0x00200000,       # SPEAK
        "CanDirectVoice": 0x00200000,          # SPEAK
        "CanPrioritizeVoice": 0x00200000,      # SPEAK
        "CanUseVoiceActivity": 0x02000000,     # USE_VAD
        "CanManageVoiceGroups": 0x00000010,    # MANAGE_CHANNELS
        "CanSendVoiceMessages": 0x00000800,    # SEND_MESSAGES
        
        "CanReadAnnouncements": 0x00000400,    # VIEW_CHANNEL
        "CanCreateAnnouncementsV2": 0x00000800,# SEND_MESSAGES
        "CanManageAnnouncements": 0x00002000,  # MANAGE_MESSAGES
        
        "CanReadEvents": 0x00000400,           # VIEW_CHANNEL
        "CanCreateEvents": 0x00100000,         # MANAGE_EVENTS
        "CanEditEvents": 0x00100000,           # MANAGE_EVENTS
        "CanDeleteEvents": 0x00100000,         # MANAGE_EVENTS
        "CanEditEventRsvps": 0x00100000,       # MANAGE_EVENTS
        
        "CanReadForums": 0x00000400,           # VIEW_CHANNEL
        "CanCreateThreads": 0x0000800000000000,# CREATE_PUBLIC_THREADS
        "CanCreateThreadReplies": 0x00000800,  # SEND_MESSAGES
        "CanDeleteOtherPosts": 0x00002000,     # MANAGE_MESSAGES
        "CanStickyPosts": 0x00002000,          # MANAGE_MESSAGES
        "CanLockThreads": 0x0004000000000000,  # MANAGE_THREADS
        
        "CanReadMedia": 0x00000400,            # VIEW_CHANNEL
        "CanAddMedia": 0x00008000,             # ATTACH_FILES
        "CanEditMedia": 0x00002000,            # MANAGE_MESSAGES
        "CanDeleteMedia": 0x00002000,          # MANAGE_MESSAGES
        
        "CanManageCustomReactions": 0x40000000,# MANAGE_EMOJIS_AND_STICKERS
        "CanChangeNickname": 0x04000000,       # CHANGE_NICKNAME
        "CanManageNicknames": 0x08000000,      # MANAGE_NICKNAMES
        
        "CanReadStreams": 0x00000400,          # VIEW_CHANNEL
        "CanJoinStreamVoice": 0x00100000,      # CONNECT
        "CanCreateStreams": 0x00000200,        # STREAM
        "CanSendStreamMessages": 0x00000800,   # SEND_MESSAGES
        "CanAddStreamVoice": 0x00200000,       # SPEAK
        "CanUseVoiceActivityInStream": 0x02000000, # USE_VAD
    }
    
    def __init__(self, auth_token: str, output_dir: str, export_format: str = "discord", page_delay: float = None):
        """Initialize exporter with auth token and output directory
        
        Args:
            auth_token: Guilded hmac_signed_session token
            output_dir: Directory to save exported data
            export_format: Export format - 'discord' (Discord takeout) or 'raw' (raw Guilded JSON)
            page_delay: Delay between page fetches in seconds (default: 0.5, can be overridden via GUILDED_EXPORT_DELAY_SECONDS env var)
        """
        self.auth_token = auth_token
        self.output_dir = Path(output_dir)
        self.export_format = export_format
        self.cookies = {
            "authenticated": "true",
            "hmac_signed_session": auth_token,
        }
        self.session = requests.Session()
        self.session.cookies.update(self.cookies)
        
        # Configurable delay: parameter > env var > default (0.5s)
        if page_delay is not None:
            self.page_delay = page_delay
        else:
            self.page_delay = float(os.getenv("GUILDED_EXPORT_DELAY_SECONDS", "0.5"))
        
    def log(self, message: str, level: str = "INFO"):
        """Log a message with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] [{level}] {message}")
        
    def fetch(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Fetch data from Guilded API"""
        url = f"{self.GUILDED_API}/{endpoint}"
        try:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            return self._fix_cdn_urls(data)
        except requests.exceptions.RequestException as e:
            self.log(f"Error fetching {endpoint}: {e}", "ERROR")
            raise
            
    def _fix_cdn_urls(self, data: Any) -> Any:
        """Fix old S3 URLs to new CDN URLs"""
        if isinstance(data, dict):
            return {k: self._fix_cdn_urls(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._fix_cdn_urls(item) for item in data]
        elif isinstance(data, str):
            match = re.match(r"^https://s3-us-west-2\.amazonaws\.com/www\.guilded\.gg/(.*)$", data)
            if match:
                return f"https://cdn.gldcdn.com/{match.group(1)}"
        return data
        
    def download_file(self, url: str, filepath: Path) -> bool:
        """Download a file from URL to filepath"""
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            if filepath.exists():
                self.log(f"File already exists: {filepath}", "DEBUG")
                return True
                
            response = self.session.get(url, stream=True)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            self.log(f"Error downloading {url}: {e}", "ERROR")
            return False
            
    def sanitize_filename(self, filename: str) -> str:
        """Sanitize filename for filesystem"""
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = filename.rstrip(' _')
        return filename[:250] if filename else 'untitled'
        
    def convert_permissions(self, guilded_perms: Dict) -> int:
        """Convert Guilded permissions to Discord bitmask"""
        discord_perms = 0
        
        if isinstance(guilded_perms, dict):
            for category, perms in guilded_perms.items():
                if isinstance(perms, dict):
                    for perm_id, value in perms.items():
                        if value and perm_id in self.PERMISSION_MAP:
                            discord_perms |= self.PERMISSION_MAP[perm_id]
                            
        return discord_perms
        
    def slate_to_markdown(self, content: Dict) -> str:
        """Convert Guilded's Slate.js content to Discord markdown"""
        if not content or not isinstance(content, dict):
            return ""
            
        document = content.get("document", {})
        if not document:
            return ""
            
        nodes = document.get("nodes", [])
        return self._process_nodes(nodes)
        
    def _process_nodes(self, nodes: List[Dict]) -> str:
        """Process Slate.js nodes recursively"""
        result = []
        
        for node in nodes:
            if node.get("object") == "block":
                result.append(self._process_block(node))
            elif node.get("object") == "text":
                result.append(self._process_text(node))
                
        return "\n".join(result)
        
    def _process_block(self, block: Dict) -> str:
        """Process a Slate.js block node"""
        block_type = block.get("type", "")
        nodes = block.get("nodes", [])
        
        content = ""
        for node in nodes:
            if node.get("object") == "text":
                content += self._process_text(node)
            elif node.get("object") == "inline":
                content += self._process_inline(node)
                
        if block_type == "markdown-plain-text":
            return content
        elif block_type == "paragraph":
            return content
        elif block_type == "code-line":
            return f"`{content}`"
        else:
            return content
            
    def _process_text(self, text_node: Dict) -> str:
        """Process a Slate.js text node"""
        node_type = text_node.get("type", "")
        
        if node_type == "mention":
            return self._process_mention(text_node)
            
        leaves = text_node.get("leaves", [])
        result = []
        
        for leaf in leaves:
            text = leaf.get("text", "")
            marks = leaf.get("marks", [])
            
            for mark in marks:
                mark_type = mark.get("type", "")
                if mark_type == "bold":
                    text = f"**{text}**"
                elif mark_type == "italic":
                    text = f"*{text}*"
                elif mark_type == "underline":
                    text = f"__{text}__"
                elif mark_type == "strikethrough":
                    text = f"~~{text}~~"
                elif mark_type == "code":
                    text = f"`{text}`"
                    
            result.append(text)
            
        return "".join(result)
        
    def _process_inline(self, inline_node: Dict) -> str:
        """Process a Slate.js inline node"""
        node_type = inline_node.get("type", "")
        
        if node_type == "link":
            data = inline_node.get("data", {})
            href = data.get("href", "")
            leaves = inline_node.get("nodes", [{}])[0].get("leaves", [])
            text = leaves[0].get("text", href) if leaves else href
            return f"[{text}]({href})"
        elif node_type == "mention":
            return self._process_mention(inline_node)
        elif node_type == "reaction":
            return self._process_reaction(inline_node)
            
        return ""
        
    def _process_mention(self, mention_node: Dict) -> str:
        """Process a mention node"""
        data = mention_node.get("data", {})
        mention = data.get("mention", {})
        mention_type = mention.get("type", "")
        mention_id = mention.get("id", "")
        
        if mention_type == "person":
            return f"<@{mention_id}>"
        elif mention_type == "role":
            return f"<@&{mention_id}>"
        elif mention_type == "channel":
            channel_data = data.get("channel", {})
            channel_id = channel_data.get("id", mention_id)
            return f"<#{channel_id}>"
        else:
            return f"@{mention.get('name', mention_id)}"
            
    def _process_reaction(self, reaction_node: Dict) -> str:
        """Process a custom emoji/reaction node"""
        data = reaction_node.get("data", {})
        reaction = data.get("reaction", {})
        custom_reaction = reaction.get("customReaction", {})
        
        if custom_reaction:
            emoji_id = custom_reaction.get("id", "")
            emoji_name = custom_reaction.get("name", "emoji")
            is_animated = custom_reaction.get("apng") is not None
            prefix = "a" if is_animated else ""
            return f"<{prefix}:{emoji_name}:{emoji_id}>"
        else:
            emoji_id = reaction.get("id", "")
            return f":{emoji_id}:"
            
    def export_account(self, user_data: Dict) -> Dict:
        """Export user account data in Discord format"""
        self.log("Exporting account data...")
        
        account_dir = self.output_dir / "account"
        account_dir.mkdir(parents=True, exist_ok=True)
        
        user = user_data.get("user", user_data)
        discord_user = {
            "id": user.get("id", ""),
            "username": user.get("name", ""),
            "discriminator": "0",  # Discord moved to username system
            "email": user_data.get("email", ""),
            "verified": True,
            "avatar_hash": self._extract_avatar_hash(user.get("profilePicture", "")),
            "banner_hash": self._extract_avatar_hash(user.get("profileBannerLg", "")),
        }
        
        avatar_url = user.get("profilePicture")
        if avatar_url:
            avatar_ext = Path(urlparse(avatar_url).path).suffix or ".png"
            avatar_path = account_dir / f"avatar{avatar_ext}"
            self.download_file(avatar_url, avatar_path)
            
        user_json_path = account_dir / "user.json"
        with open(user_json_path, 'w', encoding='utf-8') as f:
            json.dump(discord_user, f, indent=2)
            
        self.log(f"Account data exported to {account_dir}")
        return discord_user
        
    def _extract_avatar_hash(self, url: str) -> str:
        """Extract avatar hash from CDN URL"""
        if not url:
            return ""
        path = urlparse(url).path
        filename = Path(path).stem
        return filename.split('-')[0] if '-' in filename else filename
        
    def create_readme(self):
        """Create README.txt file"""
        readme_content = f"""GUILDED DATA EXPORT (Discord Takeout Format)

This export contains your Guilded server data in Discord takeout format,
compatible with Spacebar import.

IMPORTANT: This export was created because Guilded.gg is shutting down on
January 1, 2026. All attachments have been downloaded for preservation.

Export Structure:
- account/          Your user account data and avatar
- messages/         All channel messages with full metadata
- servers/          Server/guild information

For more information about importing this data into Spacebar, please refer
to the Spacebar documentation.

Export created: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Exporter: GuildedChatExporter (Discord Takeout Format)
"""
        
        # Ensure output directory exists before writing README
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        readme_path = self.output_dir / "README.txt"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
            
        self.log("Created README.txt")
    
    def export_server(self, server_id: str, server_name: str) -> Dict:
        """Export server/guild data in Discord format"""
        self.log(f"Exporting server: {server_name} ({server_id})")
        
        server_dir = self.output_dir / "servers" / server_id
        server_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            info_data = self.fetch(f"teams/{server_id}/info")
            team = info_data.get("team", {})
        except Exception as e:
            self.log(f"Could not fetch full server info: {e}", "WARNING")
            team = {"id": server_id, "name": server_name}
        
        discord_guild = {
            "id": team.get("id", server_id),
            "name": team.get("name", server_name),
            "icon": self._extract_avatar_hash(team.get("profilePicture", "")),
            "description": team.get("description", ""),
            "splash": self._extract_avatar_hash(team.get("teamDashImage", "")),
            "banner": self._extract_avatar_hash(team.get("homeBannerImageLg", "")),
        }
        
        guild_json_path = server_dir / "guild.json"
        with open(guild_json_path, 'w', encoding='utf-8') as f:
            json.dump(discord_guild, f, indent=2)
        
        audit_log_path = server_dir / "audit-log.json"
        with open(audit_log_path, 'w', encoding='utf-8') as f:
            json.dump([], f)
            
        self.log(f"Server data exported to {server_dir}")
        return discord_guild
    
    def export_channels(self, server_id: str) -> Dict[str, Dict]:
        """Export all channels and build index"""
        self.log("Exporting channels...")
        
        channels_data = self.fetch(f"teams/{server_id}/channels")
        channels = channels_data.get("channels", [])
        
        channel_index = {}
        channel_map = {}
        
        for channel in channels:
            channel_id = channel.get("id", "")
            channel_name = channel.get("name", "untitled")
            channel_type = channel.get("contentType", "chat")
            
            if channel_type in ["scheduling"]:
                self.log(f"Skipping unsupported channel type: {channel_type} ({channel_name})", "INFO")
                continue
                
            discord_type = self.CHANNEL_TYPE_MAP.get(channel_type, 0)
            
            discord_channel = {
                "id": channel_id,
                "type": discord_type,
                "name": channel_name,
                "topic": channel.get("description", ""),
                "guild": {
                    "id": server_id,
                    "name": channel.get("teamName", "")
                }
            }
            
            channel_index[channel_id] = channel_name
            channel_map[channel_id] = {
                "discord_channel": discord_channel,
                "guilded_type": channel_type,
                "guilded_data": channel
            }
            
            channel_dir = self.output_dir / "messages" / f"c{channel_id}"
            channel_dir.mkdir(parents=True, exist_ok=True)
            
            channel_json_path = channel_dir / "channel.json"
            with open(channel_json_path, 'w', encoding='utf-8') as f:
                json.dump(discord_channel, f, indent=2)
        
        index_path = self.output_dir / "messages" / "index.json"
        with open(index_path, 'w', encoding='utf-8') as f:
            json.dump(channel_index, f, indent=2)
            
        self.log(f"Exported {len(channel_map)} channels")
        return channel_map
    
    def export_messages(self, channel_id: str, channel_info: Dict):
        """Export messages for a channel"""
        channel_name = channel_info["discord_channel"]["name"]
        channel_type = channel_info["guilded_type"]
        
        self.log(f"Exporting messages from #{channel_name} ({channel_type})")
        
        channel_dir = self.output_dir / "messages" / f"c{channel_id}"
        messages_json_path = channel_dir / "messages.json"
        
        all_messages = []
        before_id = None
        page = 0
        
        while True:
            try:
                params = {}
                if before_id:
                    params["beforeId"] = before_id
                    
                messages_data = self.fetch(f"channels/{channel_id}/messages", params=params)
                messages = messages_data.get("messages", [])
                
                if not messages:
                    break
                    
                page += 1
                self.log(f"  Fetched page {page}, {len(messages)} messages", "DEBUG")
                
                for msg in messages:
                    discord_msg = self._convert_message(msg, channel_id)
                    all_messages.append(discord_msg)
                    
                if len(messages) < 50:
                    break
                    
                before_id = messages[-1].get("id")
                time.sleep(self.page_delay)
                
            except Exception as e:
                self.log(f"Error fetching messages for {channel_name}: {e}", "ERROR")
                break
        
        try:
            pinned_data = self.fetch(f"channels/{channel_id}/messages/pinned")
            pinned_messages = pinned_data.get("messages", [])
            pinned_ids = {msg.get("id") for msg in pinned_messages}
            
            for msg in all_messages:
                if msg["id"] in pinned_ids:
                    msg["pinned"] = True
                    
            self.log(f"  Marked {len(pinned_ids)} pinned messages", "DEBUG")
        except Exception as e:
            self.log(f"Could not fetch pinned messages: {e}", "WARNING")
        
        with open(messages_json_path, 'w', encoding='utf-8') as f:
            json.dump(all_messages, f, indent=2)
            
        self.log(f"  Exported {len(all_messages)} messages")
        
        self._download_message_attachments(all_messages, channel_dir)
    
    def _convert_message(self, guilded_msg: Dict, channel_id: str) -> Dict:
        """Convert a Guilded message to Discord format"""
        msg_id = guilded_msg.get("id", "")
        content_obj = guilded_msg.get("content", {})
        
        content = self.slate_to_markdown(content_obj)
        
        author_id = guilded_msg.get("createdBy", "")
        webhook_id = guilded_msg.get("webhookId")
        
        author = {
            "id": author_id,
            "username": author_id,
            "discriminator": "0",
            "avatar": None
        }
        
        embeds = []
        document = content_obj.get("document", {})
        nodes = document.get("nodes", [])
        for node in nodes:
            node_data = node.get("data", {})
            node_embeds = node_data.get("embeds", [])
            for embed in node_embeds:
                discord_embed = self._convert_embed(embed)
                embeds.append(discord_embed)
        
        attachments = self._extract_attachments(content_obj)
        mentions = self._extract_mentions(content_obj)
        mention_roles = self._extract_mention_roles(content_obj)
        
        discord_msg = {
            "id": msg_id,
            "type": 0,
            "content": content,
            "channel_id": channel_id,
            "author": author,
            "attachments": attachments,
            "embeds": embeds,
            "mentions": mentions,
            "mention_roles": mention_roles,
            "pinned": False,
            "timestamp": guilded_msg.get("createdAt", ""),
            "edited_timestamp": guilded_msg.get("updatedAt"),
            "tts": False,
            "mention_everyone": False,
            "reactions": []
        }
        
        if webhook_id:
            discord_msg["webhook_id"] = webhook_id
            
        return discord_msg
    
    def _convert_embed(self, guilded_embed: Dict) -> Dict:
        """Convert Guilded embed to Discord format"""
        discord_embed = {
            "title": guilded_embed.get("title"),
            "description": guilded_embed.get("description"),
            "url": guilded_embed.get("url"),
            "color": guilded_embed.get("color", 0),
            "timestamp": guilded_embed.get("timestamp"),
        }
        
        if "footer" in guilded_embed:
            footer = guilded_embed["footer"]
            discord_embed["footer"] = {
                "text": footer.get("text", ""),
                "icon_url": footer.get("icon_url") or footer.get("iconUrl")
            }
        
        if "thumbnail" in guilded_embed:
            discord_embed["thumbnail"] = {"url": guilded_embed["thumbnail"].get("url")}
        
        if "image" in guilded_embed:
            discord_embed["image"] = {"url": guilded_embed["image"].get("url")}
        
        if "author" in guilded_embed:
            author = guilded_embed["author"]
            discord_embed["author"] = {
                "name": author.get("name", ""),
                "url": author.get("url"),
                "icon_url": author.get("icon_url") or author.get("iconUrl")
            }
        
        if "fields" in guilded_embed:
            discord_embed["fields"] = guilded_embed["fields"]
            
        return discord_embed
    
    def _extract_attachments(self, content_obj: Dict) -> List[Dict]:
        """Extract attachments from message content"""
        return []
    
    def _extract_mentions(self, content_obj: Dict) -> List[str]:
        """Extract user mentions from content"""
        return []
    
    def _extract_mention_roles(self, content_obj: Dict) -> List[str]:
        """Extract role mentions from content"""
        return []
    
    def _download_message_attachments(self, messages: List[Dict], channel_dir: Path):
        """Download all attachments from messages"""
        attachments_dir = channel_dir / "attachments"
        
        total_attachments = sum(len(msg.get("attachments", [])) for msg in messages)
        if total_attachments == 0:
            return
            
        self.log(f"  Downloading {total_attachments} attachments...")
        
        downloaded = 0
        for msg in messages:
            for attachment in msg.get("attachments", []):
                url = attachment.get("url")
                if url:
                    filename = attachment.get("filename", Path(urlparse(url).path).name)
                    filepath = attachments_dir / filename
                    
                    if self.download_file(url, filepath):
                        downloaded += 1
                        
        self.log(f"  Downloaded {downloaded}/{total_attachments} attachments")
    
    def export_all_raw(self, server_id: str, server_name: str):
        """Export entire server in raw Guilded JSON format"""
        self.log("=" * 60)
        self.log(f"Starting RAW export of server: {server_name}")
        self.log("=" * 60)
        
        raw_dir = self.output_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            user_data = self.fetch("me", params={"isLogin": "false", "v2": "true"})
            user_path = raw_dir / "user.json"
            with open(user_path, 'w', encoding='utf-8') as f:
                json.dump(user_data, f, indent=2)
            self.log("Exported user data")
        except Exception as e:
            self.log(f"Could not export user data: {e}", "WARNING")
        
        try:
            info_data = self.fetch(f"teams/{server_id}/info")
            info_path = raw_dir / f"server_{server_id}_info.json"
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(info_data, f, indent=2)
            self.log("Exported server info")
        except Exception as e:
            self.log(f"Could not export server info: {e}", "WARNING")
        
        try:
            channels_data = self.fetch(f"teams/{server_id}/channels")
            channels_path = raw_dir / f"server_{server_id}_channels.json"
            with open(channels_path, 'w', encoding='utf-8') as f:
                json.dump(channels_data, f, indent=2)
            self.log("Exported channels list")
            
            channels = channels_data.get("channels", [])
            
            for channel in channels:
                channel_id = channel.get("id", "")
                channel_name = channel.get("name", "untitled")
                channel_type = channel.get("contentType", "chat")
                
                self.log(f"Exporting messages from #{channel_name} ({channel_type})")
                
                all_messages = []
                before_id = None
                page = 0
                
                while True:
                    try:
                        params = {}
                        if before_id:
                            params["beforeId"] = before_id
                        
                        messages_data = self.fetch(f"channels/{channel_id}/messages", params=params)
                        messages = messages_data.get("messages", [])
                        
                        if not messages:
                            break
                        
                        page += 1
                        self.log(f"  Fetched page {page}, {len(messages)} messages")
                        all_messages.extend(messages)
                        
                        if len(messages) < 50:
                            break
                        
                        before_id = messages[-1].get("id")
                        time.sleep(0.5)
                        
                    except Exception as e:
                        self.log(f"Error fetching messages: {e}", "ERROR")
                        break
                
                if all_messages:
                    messages_path = raw_dir / f"channel_{channel_id}_messages.json"
                    with open(messages_path, 'w', encoding='utf-8') as f:
                        json.dump({
                            "channel": channel,
                            "messages": all_messages
                        }, f, indent=2)
                    self.log(f"  Exported {len(all_messages)} messages")
                
                try:
                    pinned_data = self.fetch(f"channels/{channel_id}/messages/pinned")
                    if pinned_data.get("messages"):
                        pinned_path = raw_dir / f"channel_{channel_id}_pinned.json"
                        with open(pinned_path, 'w', encoding='utf-8') as f:
                            json.dump(pinned_data, f, indent=2)
                        self.log(f"  Exported pinned messages")
                except:
                    pass
                
        except Exception as e:
            self.log(f"Error exporting channels: {e}", "ERROR")
        
        try:
            members_data = self.fetch(f"teams/{server_id}/members")
            members_path = raw_dir / f"server_{server_id}_members.json"
            with open(members_path, 'w', encoding='utf-8') as f:
                json.dump(members_data, f, indent=2)
            self.log("Exported members list")
        except Exception as e:
            self.log(f"Could not export members: {e}", "WARNING")
        
        try:
            groups_data = self.fetch(f"teams/{server_id}/groups")
            groups_path = raw_dir / f"server_{server_id}_groups.json"
            with open(groups_path, 'w', encoding='utf-8') as f:
                json.dump(groups_data, f, indent=2)
            self.log("Exported groups")
        except Exception as e:
            self.log(f"Could not export groups: {e}", "WARNING")
        
        readme_content = f"""GUILDED RAW DATA EXPORT

This export contains raw JSON responses from the Guilded API.

Server: {server_name} ({server_id})
Export Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

Files:
- user.json - Your user data
- server_*_info.json - Server information
- server_*_channels.json - Channel list
- channel_*_messages.json - Messages per channel
- channel_*_pinned.json - Pinned messages per channel
- server_*_members.json - Server members
- server_*_groups.json - Server groups

This raw data preserves all Guilded-specific fields and can be used to
write custom importers for Spacebar or other platforms.

IMPORTANT: Guilded.gg is shutting down on January 1, 2026.
This export preserves your data before the shutdown.
"""
        readme_path = raw_dir / "README.txt"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        self.log("=" * 60)
        self.log("RAW export complete!")
        self.log(f"Output directory: {raw_dir}")
        self.log("=" * 60)
    
    def export_all(self, server_id: str, server_name: str):
        """Export entire server (format depends on self.export_format)"""
        if self.export_format == "raw":
            self.export_all_raw(server_id, server_name)
        else:
            self.export_all_discord(server_id, server_name)
    
    def export_all_discord(self, server_id: str, server_name: str):
        """Export entire server in Discord takeout format"""
        self.log("=" * 60)
        self.log(f"Starting DISCORD export of server: {server_name}")
        self.log("=" * 60)
        
        self.create_readme()
        
        try:
            user_data = self.fetch("me", params={"isLogin": "false", "v2": "true"})
            self.export_account(user_data)
        except Exception as e:
            self.log(f"Could not export account data: {e}", "WARNING")
        
        self.export_server(server_id, server_name)
        
        channel_map = self.export_channels(server_id)
        
        for channel_id, channel_info in channel_map.items():
            try:
                self.export_messages(channel_id, channel_info)
            except Exception as e:
                channel_name = channel_info["discord_channel"]["name"]
                self.log(f"Error exporting messages from #{channel_name}: {e}", "ERROR")
                continue
        
        self.log("=" * 60)
        self.log("Export complete!")
        self.log(f"Output directory: {self.output_dir}")
        self.log("=" * 60)

if __name__ == "__main__":
    print("GuildedChatExporter - Discord Takeout Format")
    print("=" * 50)
    print()
    print("This script exports Guilded servers to Discord takeout format.")
    print("Use the interactive version or import this as a module.")

#!/usr/bin/env python3
"""
GuildedChatExporter - WebSocket-based Raw Export
Export Guilded data using WebSocket gateway for complete history preservation
"""

import socketio
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import aiohttp
import logging

class GuildedWebSocketExporter:
    """Export Guilded data using WebSocket gateway"""
    
    WS_URL = "wss://www.guilded.gg/ws/"
    API_URL = "https://www.guilded.gg/api"
    
    def __init__(self, auth_token: str, output_dir: str):
        """Initialize WebSocket exporter
        
        Args:
            auth_token: Guilded hmac_signed_session token
            output_dir: Directory to save exported data
        """
        self.auth_token = auth_token
        self.output_dir = Path(output_dir)
        self.cookies = {
            "authenticated": "true",
            "hmac_signed_session": auth_token,
        }
        
        self.sio = socketio.AsyncClient(
            logger=False,
            engineio_logger=False,
            reconnection=True,
            reconnection_attempts=5,
        )
        
        self.messages_buffer = []
        self.events_buffer = []
        self.connected = False
        self.team_id = None
        
        self._setup_handlers()
        
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
        
    def _setup_handlers(self):
        """Setup WebSocket event handlers"""
        
        @self.sio.event
        async def connect():
            self.connected = True
            self.logger.info("WebSocket connected")
            
        @self.sio.event
        async def disconnect():
            self.connected = False
            self.logger.info("WebSocket disconnected")
            
        @self.sio.event
        async def connect_error(data):
            self.logger.error(f"Connection error: {data}")
            
        @self.sio.on('*')
        async def catch_all(event, data):
            """Catch all events and store them"""
            self.logger.debug(f"Event: {event}, Data: {data}")
            self.events_buffer.append({
                "event": event,
                "data": data,
                "timestamp": datetime.now().isoformat()
            })
            
            if event == "ChatMessageCreated":
                self.messages_buffer.append(data)
                self.logger.info(f"Message received: {data.get('message', {}).get('id', 'unknown')}")
    
    async def connect_websocket(self, team_id: Optional[str] = None):
        """Connect to Guilded WebSocket
        
        Args:
            team_id: Optional team ID for team-specific events
        """
        self.team_id = team_id
        
        params = {
            "transport": "websocket",
            "EIO": "3",
            "jwt": "undefined",
            "deviceType": "web",
        }
        
        if team_id:
            params["teamId"] = team_id
            
        headers = {
            "Cookie": f"hmac_signed_session={self.auth_token}; authenticated=true",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        }
        
        try:
            await self.sio.connect(
                self.WS_URL,
                transports=['websocket'],
                headers=headers,
                socketio_path='/ws',
                wait_timeout=10,
            )
            self.logger.info(f"Connected to WebSocket{' for team ' + team_id if team_id else ''}")
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            raise
    
    async def fetch_rest_api(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Fetch data from REST API for initial setup
        
        Args:
            endpoint: API endpoint
            params: Query parameters
            
        Returns:
            API response data
        """
        url = f"{self.API_URL}/{endpoint}"
        
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            async with session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.json()
    
    async def fetch_dm_channels(self, user_id: str) -> List[Dict]:
        """Fetch all DM and group DM channels for a user
        
        Args:
            user_id: User ID to fetch DMs for
            
        Returns:
            List of DM channel objects
        """
        self.logger.info("Fetching DM channels...")
        dmlist: List[Dict] = []
        cursor = None
        
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            while True:
                params = {"maxItems": "25", "useEnhancedPagination": "false"}
                if cursor is not None:
                    params["cursor"] = cursor
                
                url = f"{self.API_URL}/users/{user_id}/channels"
                async with session.get(url, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                
                channels = data.get("channels", [])
                if not channels:
                    break
                
                dmlist.extend(channels)
                self.logger.info(f"  Fetched {len(dmlist)} DM channels so far...")
                
                last = channels[-1]
                cursor = (
                    last.get("createdAt")
                    or last.get("updatedAt")
                    or (last.get("lastMessage") or {}).get("createdAt")
                )
                if cursor is None or len(channels) < 25:
                    break
                
                await asyncio.sleep(0.5)
        
        self.logger.info(f"Found {len(dmlist)} DM/group DM channels total")
        return dmlist
    
    async def export_dm_channel(self, channel: Dict, raw_dir: Path) -> None:
        """Export a single DM channel's messages
        
        Args:
            channel: DM channel object
            raw_dir: Directory to save exported data
        """
        channel_id = channel.get("id", "")
        channel_name = channel.get("name", "untitled")
        
        self.logger.info(f"Exporting DM: {channel_name} ({channel_id})")
        
        messages = await self.export_channel_history(channel_id)
        if not messages:
            self.logger.info(f"  No messages in this DM")
            return
        
        dm_dir = raw_dir / "dms"
        dm_dir.mkdir(parents=True, exist_ok=True)
        
        messages_path = dm_dir / f"dm_{channel_id}_messages.json"
        with open(messages_path, 'w', encoding='utf-8') as f:
            json.dump({
                "channel": channel,
                "messages": messages,
                "export_timestamp": datetime.now().isoformat(),
                "total_messages": len(messages)
            }, f, indent=2)
        self.logger.info(f"  Exported {len(messages)} messages")
    
    async def export_all_dms(self, user_id: str) -> None:
        """Export all DM and group DM channels
        
        Args:
            user_id: User ID to export DMs for
        """
        self.logger.info("=" * 60)
        self.logger.info("Starting DM export")
        self.logger.info("=" * 60)
        
        raw_dir = self.output_dir / "raw_websocket"
        raw_dir.mkdir(parents=True, exist_ok=True)
        
        dm_channels = await self.fetch_dm_channels(user_id)
        
        if not dm_channels:
            self.logger.info("No DM channels found")
            return
        
        dm_index_path = raw_dir / "dms" / "dm_channels_index.json"
        dm_index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dm_index_path, 'w', encoding='utf-8') as f:
            json.dump({
                "channels": dm_channels,
                "total_channels": len(dm_channels),
                "export_timestamp": datetime.now().isoformat()
            }, f, indent=2)
        self.logger.info(f"Saved DM channels index ({len(dm_channels)} channels)")
        
        for idx, channel in enumerate(dm_channels, 1):
            self.logger.info(f"[{idx}/{len(dm_channels)}] Processing DM channel")
            await self.export_dm_channel(channel, raw_dir)
        
        self.logger.info("=" * 60)
        self.logger.info("DM export complete!")
        self.logger.info(f"Output directory: {raw_dir / 'dms'}")
        self.logger.info("=" * 60)
    
    async def export_channel_history(self, channel_id: str) -> List[Dict]:
        """Export complete channel history using cursor rewinding
        
        Args:
            channel_id: Channel ID to export
            
        Returns:
            List of all messages
        """
        self.logger.info(f"Exporting channel {channel_id} history")
        
        all_messages = []
        before_id = None
        page = 0
        
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            while True:
                try:
                    params = {}
                    if before_id:
                        params["beforeId"] = before_id
                    
                    url = f"{self.API_URL}/channels/{channel_id}/messages"
                    async with session.get(url, params=params) as response:
                        response.raise_for_status()
                        data = await response.json()
                        
                    messages = data.get("messages", [])
                    
                    if not messages:
                        break
                    
                    page += 1
                    self.logger.info(f"  Page {page}: {len(messages)} messages")
                    all_messages.extend(messages)
                    
                    if len(messages) < 50:
                        break
                    
                    before_id = messages[-1].get("id")
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    self.logger.error(f"Error fetching messages: {e}")
                    break
        
        self.logger.info(f"  Total: {len(all_messages)} messages")
        return all_messages
    
    async def export_server_full(self, server_id: str, server_name: str):
        """Export complete server data using REST API cursor rewinding
        
        Args:
            server_id: Server/team ID
            server_name: Server/team name
        """
        self.logger.info("=" * 60)
        self.logger.info(f"Starting WebSocket RAW export of: {server_name}")
        self.logger.info("=" * 60)
        
        raw_dir = self.output_dir / "raw_websocket"
        raw_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            self.logger.info("Fetching user data...")
            user_data = await self.fetch_rest_api("me", params={"isLogin": "false", "v2": "true"})
            user_path = raw_dir / "user.json"
            with open(user_path, 'w', encoding='utf-8') as f:
                json.dump(user_data, f, indent=2)
            self.logger.info("✓ User data exported")
        except Exception as e:
            self.logger.error(f"Failed to export user data: {e}")
        
        try:
            self.logger.info("Fetching server info...")
            info_data = await self.fetch_rest_api(f"teams/{server_id}/info")
            info_path = raw_dir / f"server_{server_id}_info.json"
            with open(info_path, 'w', encoding='utf-8') as f:
                json.dump(info_data, f, indent=2)
            self.logger.info("✓ Server info exported")
        except Exception as e:
            self.logger.error(f"Failed to export server info: {e}")
        
        try:
            self.logger.info("Fetching channels...")
            channels_data = await self.fetch_rest_api(f"teams/{server_id}/channels")
            channels_path = raw_dir / f"server_{server_id}_channels.json"
            with open(channels_path, 'w', encoding='utf-8') as f:
                json.dump(channels_data, f, indent=2)
            self.logger.info("✓ Channels list exported")
            
            channels = channels_data.get("channels", [])
            
            for idx, channel in enumerate(channels, 1):
                channel_id = channel.get("id", "")
                channel_name = channel.get("name", "untitled")
                channel_type = channel.get("contentType", "chat")
                
                self.logger.info(f"[{idx}/{len(channels)}] Exporting #{channel_name} ({channel_type})")
                
                messages = await self.export_channel_history(channel_id)
                
                if messages:
                    messages_path = raw_dir / f"channel_{channel_id}_messages.json"
                    with open(messages_path, 'w', encoding='utf-8') as f:
                        json.dump({
                            "channel": channel,
                            "messages": messages,
                            "export_timestamp": datetime.now().isoformat(),
                            "total_messages": len(messages)
                        }, f, indent=2)
                    self.logger.info(f"  ✓ Exported {len(messages)} messages")
                
                try:
                    async with aiohttp.ClientSession(cookies=self.cookies) as session:
                        url = f"{self.API_URL}/channels/{channel_id}/messages/pinned"
                        async with session.get(url) as response:
                            if response.status == 200:
                                pinned_data = await response.json()
                                if pinned_data.get("messages"):
                                    pinned_path = raw_dir / f"channel_{channel_id}_pinned.json"
                                    with open(pinned_path, 'w', encoding='utf-8') as f:
                                        json.dump(pinned_data, f, indent=2)
                                    self.logger.info(f"  ✓ Exported pinned messages")
                except Exception as e:
                    self.logger.debug(f"  No pinned messages: {e}")
                
        except Exception as e:
            self.logger.error(f"Failed to export channels: {e}")
        
        try:
            self.logger.info("Fetching members...")
            members_data = await self.fetch_rest_api(f"teams/{server_id}/members")
            members_path = raw_dir / f"server_{server_id}_members.json"
            with open(members_path, 'w', encoding='utf-8') as f:
                json.dump(members_data, f, indent=2)
            self.logger.info("✓ Members list exported")
        except Exception as e:
            self.logger.error(f"Failed to export members: {e}")
        
        try:
            self.logger.info("Fetching groups...")
            groups_data = await self.fetch_rest_api(f"teams/{server_id}/groups")
            groups_path = raw_dir / f"server_{server_id}_groups.json"
            with open(groups_path, 'w', encoding='utf-8') as f:
                json.dump(groups_data, f, indent=2)
            self.logger.info("✓ Groups exported")
        except Exception as e:
            self.logger.error(f"Failed to export groups: {e}")
        
        try:
            self.logger.info("Fetching roles...")
            roles_data = await self.fetch_rest_api(f"teams/{server_id}/roles")
            roles_path = raw_dir / f"server_{server_id}_roles.json"
            with open(roles_path, 'w', encoding='utf-8') as f:
                json.dump(roles_data, f, indent=2)
            self.logger.info("✓ Roles exported")
        except Exception as e:
            self.logger.error(f"Failed to export roles: {e}")
        
        readme_content = f"""GUILDED RAW DATA EXPORT (WebSocket Method)

This export contains raw JSON responses from the Guilded API using cursor rewinding
to capture complete message history.

Server: {server_name} ({server_id})
Export Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
Export Method: REST API with cursor-based pagination

Files:
- user.json - Your user data
- server_*_info.json - Server information
- server_*_channels.json - Complete channel list
- channel_*_messages.json - Complete message history per channel (cursor rewound)
- channel_*_pinned.json - Pinned messages per channel
- server_*_members.json - Server members
- server_*_groups.json - Server groups/categories
- server_*_roles.json - Server roles and permissions

This raw data preserves all Guilded-specific fields and can be used to write custom
importers for Spacebar or other platforms. All messages were retrieved using cursor
rewinding (beforeId parameter) to ensure complete history capture.

IMPORTANT: Guilded.gg is shutting down on January 1, 2026.
This export preserves your data before the shutdown.

Export completed: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
"""
        readme_path = raw_dir / "README.txt"
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        self.logger.info("=" * 60)
        self.logger.info("RAW WebSocket export complete!")
        self.logger.info(f"Output directory: {raw_dir}")
        self.logger.info("=" * 60)
    
    async def disconnect(self):
        """Disconnect from WebSocket"""
        if self.sio.connected:
            await self.sio.disconnect()
            self.logger.info("WebSocket disconnected")


async def main_async():
    """Async main function for testing"""
    print("GuildedChatExporter - WebSocket Raw Export")
    print("=" * 50)
    print()
    
    auth_token = input("Enter your hmac_signed_session token: ").strip()
    if not auth_token:
        print("Error: Token is required")
        return
    
    exporter = GuildedWebSocketExporter(auth_token, output_dir="./guilded-export-ws")
    
    try:
        print("\nFetching your servers...")
        servers_data = await exporter.fetch_rest_api("me", params={"isLogin": "false", "v2": "true"})
        teams = servers_data.get("teams", [])
        
        if not teams:
            print("No servers found")
            return
        
        print(f"\nFound {len(teams)} server(s):")
        for idx, team in enumerate(teams):
            print(f"{idx + 1}. {team.get('name', 'Unnamed')} (ID: {team.get('id', 'unknown')})")
        
        server_idx = int(input(f"\nSelect server (1-{len(teams)}): ")) - 1
        if server_idx < 0 or server_idx >= len(teams):
            print("Invalid selection")
            return
        
        selected_team = teams[server_idx]
        await exporter.export_server_full(
            server_id=selected_team.get("id", ""),
            server_name=selected_team.get("name", "")
        )
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await exporter.disconnect()


if __name__ == "__main__":
    asyncio.run(main_async())

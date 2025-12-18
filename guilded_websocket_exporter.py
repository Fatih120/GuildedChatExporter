#!/usr/bin/env python3
"""
GuildedChatExporter - WebSocket-based Raw Export
Export Guilded data using WebSocket gateway for complete history preservation
"""

import socketio
import asyncio
import json
import time
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import aiohttp
import logging

class GuildedWebSocketExporter:
    """Export Guilded data using WebSocket gateway"""
    
    WS_URL = "wss://www.guilded.gg/ws/"
    API_URL = "https://www.guilded.gg/api"
    
    def __init__(self, auth_token: str, output_dir: str, page_delay: float = None):
        """Initialize WebSocket exporter
        
        Args:
            auth_token: Guilded hmac_signed_session token
            output_dir: Directory to save exported data
            page_delay: Delay between page fetches in seconds (default: 0.5, can be overridden via GUILDED_EXPORT_DELAY_SECONDS env var)
        """
        self.auth_token = auth_token
        self.output_dir = Path(output_dir)
        self.cookies = {
            "authenticated": "true",
            "hmac_signed_session": auth_token,
        }
        
        # Configurable delay: parameter > env var > default (0.5s)
        if page_delay is not None:
            self.page_delay = page_delay
        else:
            self.page_delay = float(os.getenv("GUILDED_EXPORT_DELAY_SECONDS", "0.5"))
        
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
                
                await asyncio.sleep(self.page_delay)
        
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
    
    def _get_checkpoint_path(self, server_id: str) -> Path:
        """Get path to checkpoint file for a server"""
        raw_dir = self.output_dir / "raw_websocket"
        return raw_dir / f"server_{server_id}_checkpoint.json"
    
    def _load_checkpoint(self, server_id: str) -> Optional[Dict]:
        """Load checkpoint for a server if it exists"""
        checkpoint_path = self._get_checkpoint_path(server_id)
        if checkpoint_path.exists():
            try:
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"Could not load checkpoint: {e}")
        return None
    
    def _save_checkpoint(self, server_id: str, checkpoint: Dict) -> None:
        """Save checkpoint atomically (write to temp file then rename)"""
        checkpoint_path = self._get_checkpoint_path(server_id)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        
        checkpoint["last_updated_at"] = datetime.now().isoformat()
        
        # Write atomically: temp file then rename
        tmp_path = checkpoint_path.with_suffix('.json.tmp')
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(checkpoint, f, indent=2)
        os.replace(tmp_path, checkpoint_path)
    
    def _save_page_file(self, raw_dir: Path, channel_id: str, page: int, messages: List[Dict]) -> None:
        """Save a page of messages atomically"""
        page_path = raw_dir / f"channel_{channel_id}_page_{page}.json"
        tmp_path = page_path.with_suffix('.json.tmp')
        
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(messages, f, indent=2)
        os.replace(tmp_path, page_path)
    
    def _load_existing_pages(self, raw_dir: Path, channel_id: str) -> tuple[List[Dict], int, Optional[str]]:
        """Load existing page files for a channel to resume export
        
        Returns:
            Tuple of (all_messages, last_page_number, last_message_id)
        """
        all_messages = []
        page = 0
        last_message_id = None
        
        while True:
            page_path = raw_dir / f"channel_{channel_id}_page_{page + 1}.json"
            if not page_path.exists():
                break
            
            try:
                with open(page_path, 'r', encoding='utf-8') as f:
                    page_messages = json.load(f)
                all_messages.extend(page_messages)
                page += 1
                if page_messages:
                    last_message_id = page_messages[-1].get("id")
                self.logger.info(f"  Loaded existing page {page} ({len(page_messages)} messages)")
            except Exception as e:
                self.logger.warning(f"  Could not load page {page + 1}: {e}")
                break
        
        return all_messages, page, last_message_id
    
    def _merge_and_cleanup_pages(self, raw_dir: Path, channel_id: str, channel: Dict, all_messages: List[Dict]) -> None:
        """Merge page files into final messages.json and clean up page files"""
        messages_path = raw_dir / f"channel_{channel_id}_messages.json"
        
        with open(messages_path, 'w', encoding='utf-8') as f:
            json.dump({
                "channel": channel,
                "messages": all_messages,
                "export_timestamp": datetime.now().isoformat(),
                "total_messages": len(all_messages)
            }, f, indent=2)
        
        # Clean up page files
        page = 1
        while True:
            page_path = raw_dir / f"channel_{channel_id}_page_{page}.json"
            if page_path.exists():
                page_path.unlink()
                page += 1
            else:
                break
        
        if page > 1:
            self.logger.info(f"  Cleaned up {page - 1} page files")
    
    async def fetch_channel_threads(self, channel_id: str) -> List[Dict]:
        """Fetch all threads (active and archived) for a channel
        
        Args:
            channel_id: Channel ID to fetch threads for
            
        Returns:
            List of thread objects
        """
        all_threads = []
        
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            for status in ["active", "archived"]:
                cursor = None
                while True:
                    params = {
                        "status": status,
                        "maxItems": "50",
                        "maxUsers": "10"
                    }
                    if cursor:
                        params["beforeDate"] = cursor
                    
                    try:
                        url = f"{self.API_URL}/channels/{channel_id}/threads"
                        async with session.get(url, params=params) as response:
                            if response.status != 200:
                                break
                            data = await response.json()
                        
                        threads_batch = data.get("threads", [])
                        if not threads_batch:
                            break
                        
                        all_threads.extend(threads_batch)
                        
                        if len(threads_batch) < 50:
                            break
                        
                        cursor = threads_batch[-1].get("createdAt")
                        await asyncio.sleep(self.page_delay)
                        
                    except Exception as e:
                        self.logger.debug(f"Error fetching threads for {channel_id}: {e}")
                        break
        
        return all_threads
    
    async def export_thread(self, thread: Dict, threads_dir: Path) -> int:
        """Export a single thread's messages
        
        Args:
            thread: Thread object
            threads_dir: Directory to save thread data
            
        Returns:
            Number of messages exported
        """
        thread_id = thread.get("id", "")
        thread_name = thread.get("name", "Untitled")
        
        thread_dir = threads_dir / thread_id
        thread_dir.mkdir(parents=True, exist_ok=True)
        
        # Save thread metadata
        info_path = thread_dir / f"{thread_id}_info.json"
        with open(info_path, 'w', encoding='utf-8') as f:
            json.dump(thread, f, indent=2)
        
        # Fetch thread messages using the same cursor-based pagination
        messages = []
        before_date = None
        
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            while True:
                params = {"limit": "100"}
                if before_date:
                    params["beforeDate"] = before_date
                
                try:
                    url = f"{self.API_URL}/channels/{thread_id}/messages"
                    async with session.get(url, params=params) as response:
                        if response.status != 200:
                            break
                        data = await response.json()
                    
                    batch = data.get("messages", [])
                    messages.extend(batch)
                    
                    if len(batch) < 100:
                        break
                    
                    before_date = batch[-1].get("createdAt")
                    await asyncio.sleep(self.page_delay)
                    
                except Exception as e:
                    self.logger.error(f"Error fetching messages for thread {thread_id}: {e}")
                    break
        
        # Reverse to get chronological order
        messages.reverse()
        
        # Save messages
        messages_path = thread_dir / f"{thread_id}_messages.json"
        with open(messages_path, 'w', encoding='utf-8') as f:
            json.dump({
                "thread": thread,
                "messages": messages,
                "export_timestamp": datetime.now().isoformat(),
                "total_messages": len(messages)
            }, f, indent=2)
        
        return len(messages)
    
    async def export_channel_threads(self, channel_id: str, channel_name: str, 
                                      channel_dir: Path) -> int:
        """Export all threads for a channel
        
        Args:
            channel_id: Channel ID
            channel_name: Channel name for logging
            channel_dir: Directory where channel data is stored
            
        Returns:
            Total number of threads exported
        """
        threads = await self.fetch_channel_threads(channel_id)
        
        if not threads:
            return 0
        
        self.logger.info(f"  Found {len(threads)} threads in #{channel_name}")
        
        threads_dir = channel_dir / "threads"
        threads_dir.mkdir(parents=True, exist_ok=True)
        
        # Save threads metadata
        metadata_path = threads_dir / f"{channel_id}_threads_metadata.json"
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump({
                "channel_id": channel_id,
                "threads": threads,
                "total_threads": len(threads),
                "export_timestamp": datetime.now().isoformat()
            }, f, indent=2)
        
        total_messages = 0
        for idx, thread in enumerate(threads, 1):
            thread_id = thread.get("id", "")
            thread_name = thread.get("name", "Untitled")
            self.logger.info(f"    [{idx}/{len(threads)}] Exporting thread: {thread_name}")
            
            msg_count = await self.export_thread(thread, threads_dir)
            total_messages += msg_count
            self.logger.info(f"      Exported {msg_count} messages")
        
        return len(threads)

    async def export_channel_history(self, channel_id: str, raw_dir: Path = None, 
                                      channel: Dict = None, checkpoint: Dict = None,
                                      server_id: str = None) -> List[Dict]:
        """Export complete channel history using cursor rewinding with resume support
        
        Args:
            channel_id: Channel ID to export
            raw_dir: Directory to save page files (optional, enables incremental saving)
            channel: Channel metadata (optional, for final merge)
            checkpoint: Checkpoint dict to update (optional)
            server_id: Server ID for checkpoint saving (optional)
            
        Returns:
            List of all messages
        """
        self.logger.info(f"Exporting channel {channel_id} history")
        
        all_messages = []
        before_id = None
        page = 0
        
        # Check for existing progress if raw_dir is provided
        if raw_dir:
            existing_messages, existing_pages, last_id = self._load_existing_pages(raw_dir, channel_id)
            if existing_pages > 0:
                all_messages = existing_messages
                page = existing_pages
                before_id = last_id
                self.logger.info(f"  Resuming from page {page + 1}, {len(all_messages)} messages already fetched")
        
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
                    self.logger.info(f"  Page {page}: {len(messages)} messages (total: {len(all_messages) + len(messages)})")
                    all_messages.extend(messages)
                    
                    # Save page file incrementally if raw_dir is provided
                    if raw_dir:
                        self._save_page_file(raw_dir, channel_id, page, messages)
                        
                        # Update checkpoint
                        if checkpoint and server_id:
                            if "channels" not in checkpoint:
                                checkpoint["channels"] = {}
                            checkpoint["channels"][channel_id] = {
                                "status": "in_progress",
                                "pages_fetched": page,
                                "messages_exported": len(all_messages),
                                "last_message_id": messages[-1].get("id")
                            }
                            self._save_checkpoint(server_id, checkpoint)
                    
                    if len(messages) < 50:
                        break
                    
                    before_id = messages[-1].get("id")
                    await asyncio.sleep(self.page_delay)
                    
                except Exception as e:
                    self.logger.error(f"Error fetching messages: {e}")
                    break
        
        self.logger.info(f"  Total: {len(all_messages)} messages")
        return all_messages
    
    async def export_server_full(self, server_id: str, server_name: str, resume: bool = True):
        """Export complete server data using REST API cursor rewinding
        
        Args:
            server_id: Server/team ID
            server_name: Server/team name
            resume: Whether to resume from checkpoint if available (default: True)
        """
        self.logger.info("=" * 60)
        self.logger.info(f"Starting WebSocket RAW export of: {server_name}")
        self.logger.info(f"Page delay: {self.page_delay}s (set GUILDED_EXPORT_DELAY_SECONDS to adjust)")
        self.logger.info("=" * 60)
        
        raw_dir = self.output_dir / "raw_websocket"
        raw_dir.mkdir(parents=True, exist_ok=True)
        
        # Load or create checkpoint
        checkpoint = None
        if resume:
            checkpoint = self._load_checkpoint(server_id)
            if checkpoint:
                done_count = sum(1 for c in checkpoint.get("channels", {}).values() if c.get("status") == "done")
                in_progress = [cid for cid, c in checkpoint.get("channels", {}).items() if c.get("status") == "in_progress"]
                self.logger.info(f"Resuming from checkpoint: {done_count} channels done, {len(in_progress)} in progress")
        
        if not checkpoint:
            checkpoint = {
                "version": 1,
                "server_id": server_id,
                "server_name": server_name,
                "export_format": "raw",
                "created_at": datetime.now().isoformat(),
                "channels": {}
            }
        
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
                
                # Check if channel is already done in checkpoint
                channel_status = checkpoint.get("channels", {}).get(channel_id, {})
                if channel_status.get("status") == "done":
                    # Also check if final messages.json exists
                    messages_path = raw_dir / f"channel_{channel_id}_messages.json"
                    if messages_path.exists():
                        self.logger.info(f"[{idx}/{len(channels)}] Skipping #{channel_name} (already exported)")
                        continue
                
                self.logger.info(f"[{idx}/{len(channels)}] Exporting #{channel_name} ({channel_type})")
                
                # Use checkpoint-aware export
                messages = await self.export_channel_history(
                    channel_id, 
                    raw_dir=raw_dir, 
                    channel=channel,
                    checkpoint=checkpoint,
                    server_id=server_id
                )
                
                if messages:
                    # Merge page files into final messages.json and clean up
                    self._merge_and_cleanup_pages(raw_dir, channel_id, channel, messages)
                    self.logger.info(f"  ✓ Exported {len(messages)} messages")
                    
                    # Mark channel as done in checkpoint
                    checkpoint["channels"][channel_id] = {
                        "status": "done",
                        "messages_exported": len(messages)
                    }
                    self._save_checkpoint(server_id, checkpoint)
                else:
                    # Mark empty channel as done
                    checkpoint["channels"][channel_id] = {
                        "status": "done",
                        "messages_exported": 0
                    }
                    self._save_checkpoint(server_id, checkpoint)
                
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
                
                # Export threads for channels that support them (chat, stream, voice)
                if channel_type in ["chat", "stream", "voice"]:
                    try:
                        channel_dir = raw_dir / f"channel_{channel_id}"
                        channel_dir.mkdir(parents=True, exist_ok=True)
                        thread_count = await self.export_channel_threads(
                            channel_id, channel_name, channel_dir
                        )
                        if thread_count > 0:
                            self.logger.info(f"  ✓ Exported {thread_count} threads")
                    except Exception as e:
                        self.logger.debug(f"  No threads or error: {e}")
                
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
- channel_*/threads/ - Thread messages for each channel (if any)
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

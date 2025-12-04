#!/usr/bin/env python3
"""
Interactive CLI for GuildedChatExporter
Export Guilded servers in Discord takeout or raw JSON format
"""

import sys
import os
import asyncio
from pathlib import Path
from guilded_to_discord_exporter import GuildedToDiscordExporter
from guilded_websocket_exporter import GuildedWebSocketExporter

def main():
    print("=" * 70)
    print("GuildedChatExporter - Discord Takeout & Raw JSON Export")
    print("Export Guilded servers before shutdown (December 19, 2025)")
    print("=" * 70)
    print()
    
    print("Export Formats:")
    print("  1. Discord Takeout - Converted to Discord format for Spacebar compatibility")
    print("  2. Raw JSON - Raw Guilded API responses (preserves all data)")
    print()
    
    while True:
        format_choice = input("Select export format (1-2): ").strip()
        if format_choice in ["1", "2"]:
            break
        print("Please enter 1 or 2")
    
    export_format = "discord" if format_choice == "1" else "raw"
    
    print()
    print("1. Get your Guilded authentication token:")
    print("   - Open Guilded in your web browser (not the app)")
    print("   - Press F12 (Chrome) or Shift+F9 (Firefox)")
    print("   - Go to Application tab > Cookies > guilded.gg")
    print("   - Find 'hmac_signed_session' and copy its value")
    print()
    
    auth_token = input("Enter your hmac_signed_session token: ").strip()
    if not auth_token:
        print("Error: Token is required")
        sys.exit(1)
    
    if export_format == "raw":
        asyncio.run(main_async_raw(auth_token))
    else:
        main_discord(auth_token)

def main_discord(auth_token: str):
    """Run Discord format export (synchronous)"""
    exporter = GuildedToDiscordExporter(auth_token, output_dir="./guilded-export", export_format="discord")
    
    print("\nFetching your servers...")
    try:
        servers_data = exporter.fetch("me", params={"isLogin": "false", "v2": "true"})
        teams = servers_data.get("teams", [])
    except Exception as e:
        print(f"Error fetching servers: {e}")
        print("Please check your authentication token and try again.")
        sys.exit(1)
    
    if not teams:
        print("No servers found in your account.")
        sys.exit(0)
    
    print(f"\nFound {len(teams)} server(s):")
    print()
    print("  0. All servers")
    for idx, team in enumerate(teams, 1):
        team_name = team.get("name", "Unnamed Server")
        team_id = team.get("id", "")
        print(f"  {idx}. {team_name} (ID: {team_id})")
    print()
    
    while True:
        selection = input(f"Select a server to export (0 for all, 1-{len(teams)}): ").strip()
        try:
            server_idx = int(selection) - 1
            if -1 <= server_idx < len(teams):
                break
            else:
                print(f"Please enter a number between 0 and {len(teams)}")
        except ValueError:
            print("Please enter a valid number")
    
    try:
        if server_idx == -1:
            print()
            print(f"Will export all {len(teams)} server(s)")
            print(f"Export directory: ./guilded-export")
            print()
            confirm = input("Start export? (y/n): ").strip().lower()
            
            if confirm != 'y':
                print("Export cancelled.")
                sys.exit(0)
            
            print()
            for idx, team in enumerate(teams, 1):
                server_id = team.get("id", "")
                server_name = team.get("name", "Unnamed Server")
                print(f"\n[{idx}/{len(teams)}] Exporting: {server_name}")
                exporter.export_all(server_id, server_name)
            
            print()
            print(f"All {len(teams)} servers exported successfully!")
            print(f"Files saved to: ./guilded-export")
        else:
            selected_team = teams[server_idx]
            server_id = selected_team.get("id", "")
            server_name = selected_team.get("name", "")
            
            print()
            print(f"Selected: {server_name}")
            print(f"Export directory: ./guilded-export")
            print()
            confirm = input("Start export? (y/n): ").strip().lower()
            
            if confirm != 'y':
                print("Export cancelled.")
                sys.exit(0)
            
            print()
            exporter.export_all(server_id, server_name)
            print()
            print("Export completed successfully!")
            print(f"Files saved to: ./guilded-export")
        
        print()
        print("Next steps:")
        print("  1. Review the exported data")
        print("  2. Import into Spacebar using the Spacebar import tools")
        print()
    except KeyboardInterrupt:
        print("\n\nExport interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during export: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

async def main_async_raw(auth_token: str):
    """Run raw JSON export (async)"""
    exporter = GuildedWebSocketExporter(auth_token, output_dir="./guilded-export")
    
    print("\nFetching your servers and user info...")
    try:
        servers_data = await exporter.fetch_rest_api("me", params={"isLogin": "false", "v2": "true"})
        teams = servers_data.get("teams", [])
        user = servers_data.get("user") or {}
        user_id = user.get("id")
    except Exception as e:
        print(f"Error fetching servers: {e}")
        print("Please check your authentication token and try again.")
        sys.exit(1)
    
    if not teams and not user_id:
        print("No servers or user info found in your account.")
        sys.exit(0)
    
    print(f"\nFound {len(teams)} server(s)")
    if user_id:
        print(f"User ID: {user_id}")
    print()
    
    print("What do you want to export?")
    print("  1. Single server")
    print("  2. All servers")
    print("  3. All DMs (and group DMs)")
    print("  4. Everything (all servers + all DMs)")
    print()
    
    while True:
        export_choice = input("Select export option (1-4): ").strip()
        if export_choice in ["1", "2", "3", "4"]:
            break
        print("Please enter 1, 2, 3, or 4")
    
    try:
        if export_choice == "1":
            await export_single_server_raw(exporter, teams)
        elif export_choice == "2":
            await export_all_servers_raw(exporter, teams)
        elif export_choice == "3":
            if not user_id:
                print("Error: Could not determine user ID for DM export")
                sys.exit(1)
            await export_all_dms_raw(exporter, user_id)
        elif export_choice == "4":
            await export_all_servers_raw(exporter, teams)
            if user_id:
                await export_all_dms_raw(exporter, user_id)
            else:
                print("Warning: Could not export DMs - user ID not found")
        
        print()
        print("Next steps:")
        print("  1. Review the exported raw JSON data")
        print("  2. Write a custom importer for Spacebar using this data")
        print("  3. All Guilded-specific fields are preserved for maximum flexibility")
        print()
    except KeyboardInterrupt:
        print("\n\nExport interrupted by user.")
        await exporter.disconnect()
        sys.exit(1)
    except Exception as e:
        print(f"\n\nError during export: {e}")
        import traceback
        traceback.print_exc()
        await exporter.disconnect()
        sys.exit(1)

async def export_single_server_raw(exporter, teams):
    """Export a single server in raw JSON format"""
    if not teams:
        print("No servers found in your account.")
        sys.exit(0)
    
    print(f"\nFound {len(teams)} server(s):")
    print()
    for idx, team in enumerate(teams, 1):
        team_name = team.get("name", "Unnamed Server")
        team_id = team.get("id", "")
        print(f"  {idx}. {team_name} (ID: {team_id})")
    print()
    
    while True:
        selection = input(f"Select a server to export (1-{len(teams)}): ").strip()
        try:
            server_idx = int(selection) - 1
            if 0 <= server_idx < len(teams):
                break
            else:
                print(f"Please enter a number between 1 and {len(teams)}")
        except ValueError:
            print("Please enter a valid number")
    
    selected_team = teams[server_idx]
    server_id = selected_team.get("id", "")
    server_name = selected_team.get("name", "")
    
    print()
    print(f"Selected: {server_name}")
    print(f"Export directory: ./guilded-export/raw_websocket")
    print()
    confirm = input("Start export? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print("Export cancelled.")
        sys.exit(0)
    
    print()
    await exporter.export_server_full(server_id, server_name)
    print()
    print("Server export completed successfully!")
    print(f"Files saved to: ./guilded-export/raw_websocket")

async def export_all_servers_raw(exporter, teams):
    """Export all servers in raw JSON format"""
    if not teams:
        print("No servers found in your account.")
        return
    
    print(f"\nWill export {len(teams)} server(s):")
    for idx, team in enumerate(teams, 1):
        team_name = team.get("name", "Unnamed Server")
        print(f"  {idx}. {team_name}")
    print()
    
    confirm = input(f"Export all {len(teams)} servers? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Export cancelled.")
        sys.exit(0)
    
    print()
    for idx, team in enumerate(teams, 1):
        server_id = team.get("id", "")
        server_name = team.get("name", "Unnamed Server")
        print(f"\n[{idx}/{len(teams)}] Exporting: {server_name}")
        await exporter.export_server_full(server_id, server_name)
    
    print()
    print(f"All {len(teams)} servers exported successfully!")
    print(f"Files saved to: ./guilded-export/raw_websocket")

async def export_all_dms_raw(exporter, user_id):
    """Export all DMs in raw JSON format"""
    print(f"\nExporting all DMs for user {user_id}...")
    print("Export directory: ./guilded-export/raw_websocket/dms")
    print()
    
    confirm = input("Start DM export? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Export cancelled.")
        return
    
    print()
    await exporter.export_all_dms(user_id)
    print()
    print("DM export completed successfully!")
    print(f"Files saved to: ./guilded-export/raw_websocket/dms")

if __name__ == "__main__":
    main()

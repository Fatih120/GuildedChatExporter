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
    print("Export Guilded servers before shutdown (January 1, 2026)")
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
    print(f"Export directory: ./guilded-export")
    print()
    confirm = input("Start export? (y/n): ").strip().lower()
    
    if confirm != 'y':
        print("Export cancelled.")
        sys.exit(0)
    
    print()
    try:
        exporter.export_all(server_id, server_name)
        print()
        print("✓ Export completed successfully!")
        print(f"✓ Files saved to: ./guilded-export")
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
    
    print("\nFetching your servers...")
    try:
        servers_data = await exporter.fetch_rest_api("me", params={"isLogin": "false", "v2": "true"})
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
    try:
        await exporter.export_server_full(server_id, server_name)
        print()
        print("✓ Export completed successfully!")
        print(f"✓ Files saved to: ./guilded-export/raw_websocket")
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

if __name__ == "__main__":
    main()

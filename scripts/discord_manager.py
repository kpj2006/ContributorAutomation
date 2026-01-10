"""
Discord manager - Handle all Discord bot operations.
"""

import argparse
import sys
import os
import requests
import json
from typing import Dict, Any

sys.path.append(os.path.dirname(__file__))
from utils import load_error_messages, load_config, format_github_issue_url, format_github_pr_url
from github import Github


class DiscordManager:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = "https://discord.com/api/v10"
        self.headers = {
            "Authorization": f"Bot {bot_token}",
            "Content-Type": "application/json"
        }
    
    def assign_role(self, guild_id: str, user_id: str, role_id: str) -> bool:
        """
        Assign role to Discord user.
        
        Edge cases:
        - User not in server
        - Bot missing permissions
        - Rate limiting
        - Invalid IDs
        """
        try:
            url = f"{self.base_url}/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
            response = requests.put(url, headers=self.headers, timeout=10)
            
            if response.status_code == 204:
                print(f"✓ Role {role_id} assigned to user {user_id}")
                return True
            elif response.status_code == 404:
                print(f"✗ User {user_id} not found in server {guild_id}")
                print(f"   Make sure the user is a member of the Discord server")
                return False
            elif response.status_code == 403:
                error_data = response.json() if response.text else {}
                error_code = error_data.get('code', 'unknown')
                error_msg = error_data.get('message', 'No details')
                print(f"✗ Permission denied (403): {error_msg} [Code: {error_code}]")
                print(f"   Troubleshooting steps:")
                print(f"   1. Bot needs 'Manage Roles' permission in server")
                print(f"   2. Bot's role must be ABOVE the role being assigned")
                print(f"   3. Check role hierarchy in Discord Server Settings → Roles")
                print(f"   4. Verify Guild ID: {guild_id}")
                print(f"   5. Verify Role ID: {role_id}")
                return False
            elif response.status_code == 429:
                # Rate limited
                retry_after = response.json().get('retry_after', 5)
                print(f"Rate limited. Retry after {retry_after}s")
                import time
                time.sleep(retry_after)
                return self.assign_role(guild_id, user_id, role_id)
            else:
                print(f"✗ Failed: {response.status_code} - {response.text}")
                return False
        
        except Exception as e:
            print(f"✗ Error assigning role: {e}")
            return False
    
    def remove_role(self, guild_id: str, user_id: str, role_id: str) -> bool:  # this for future 
        """Remove role from Discord user."""
        try:
            url = f"{self.base_url}/guilds/{guild_id}/members/{user_id}/roles/{role_id}"
            response = requests.delete(url, headers=self.headers, timeout=10)
            
            if response.status_code == 204:
                print(f"✓ Role {role_id} removed from user {user_id}")
                return True
            else:
                print(f"✗ Failed to remove role: {response.status_code}")
                return False
        
        except Exception as e:
            print(f"✗ Error removing role: {e}")
            return False
    
    def send_channel_message(self, channel_id: str, content: str) -> bool:   # for future
        """Send message to channel."""
        try:
            url = f"{self.base_url}/channels/{channel_id}/messages"
            data = {"content": content}
            response = requests.post(url, headers=self.headers, json=data, timeout=10)
            
            return response.status_code == 200
        
        except Exception as e:
            print(f"Error sending channel message: {e}")
            return False
    
    def send_dm(self, user_id: str, content: str) -> bool:   # for future
        """
        Send DM to user.
        
        Edge cases:
        - User has DMs disabled
        - User blocked bot
        - User not mutual with bot
        """
        try:
            # Create DM channel
            url = f"{self.base_url}/users/@me/channels"
            data = {"recipient_id": user_id}
            response = requests.post(url, headers=self.headers, json=data, timeout=10)
            
            if response.status_code != 200:
                print(f"Failed to create DM channel: {response.status_code}")
                return False
            
            channel_id = response.json()['id']
            
            # Send message
            return self.send_channel_message(channel_id, content)
        
        except Exception as e:
            print(f"Error sending DM: {e}")
            return False


def ask_for_info(repo_name: str, pr_number: int, pr_author: str, github_token: str):  
    """Post comment asking for Discord ID and wallet."""
    messages = load_error_messages()
    
    comment = f"""🎉 **Congratulations @{pr_author} on your first contribution!**

To complete your onboarding as an **Apprentice**, please comment exactly:

1. **Discord User ID** (17-19 digits)
2. **Wallet Address** (Ethereum format: 0x...)

**Format:**
```
discord: "YOUR_DISCORD_ID"
wallet: "YOUR_WALLET_ADDRESS"
```

**How to find your Discord ID:**
1. Enable Developer Mode (Settings → Advanced → Developer Mode)
2. Right-click your username
3. Select "Copy User ID"

**Example:**
```
discord: "123456789012345678"
wallet: "0x1234567890abcdef1234567890abcdef12345678"
```

**Discord Server:** https://discord.gg/fuuWX4AbJt
⏰ **You have 7 days to respond.**
"""
    
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        pr.create_issue_comment(comment)
        print(f"✓ Posted info request to PR #{pr_number}")
    
    except Exception as e:
        print(f"Error posting comment: {e}")


def post_success_message(repo_name: str, pr_number: int, pr_author: str,   
                        github_token: str, message_type: str):
    """Post success message to PR."""
    messages = load_error_messages()
    template = messages['success'].get(message_type, '')
    
    message = template.replace('{username}', pr_author)
    
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        pr.create_issue_comment(message)
        print(f"✓ Posted success message to PR #{pr_number}")
    
    except Exception as e:
        print(f"Error posting success message: {e}")


def main():
    parser = argparse.ArgumentParser(description='Discord management operations')
    parser.add_argument('--action', required=True, 
                       choices=['ask_info', 'assign_role', 'remove_role', 
                               'post_success', 'post_error', 'announce_good_first_issue',
                               'post_promotion', 'announce_promotion', 'post_assignment_comment',
                               'dm_sentinel_assignment', 'alert_knights_no_sentinels',
                               'post_health_summary'])
    parser.add_argument('--bot-token', help='Discord bot token')
    parser.add_argument('--guild-id', help='Discord guild ID')
    parser.add_argument('--discord-user-id', help='Discord user ID')
    parser.add_argument('--role-id', help='Discord role ID')
    parser.add_argument('--repo-name', help='Repository name')
    parser.add_argument('--pr-number', type=int, help='PR number')
    parser.add_argument('--issue-number', type=int, help='Issue number')
    parser.add_argument('--pr-author', help='PR author')
    parser.add_argument('--github-token', help='GitHub token')
    parser.add_argument('--message-type', help='Type of message to post')
    parser.add_argument('--pr-count', type=int, help='PR count for promotion')
    parser.add_argument('--username', help='Username')
    parser.add_argument('--issue-title', help='Issue title')
    parser.add_argument('--issue-labels', help='Issue labels (JSON)')
    parser.add_argument('--sentinel-username', help='Sentinel username')
    parser.add_argument('--freed', type=int, default=0)
    parser.add_argument('--reassigned', type=int, default=0)
    parser.add_argument('--escalated', type=int, default=0)
    parser.add_argument('--warnings', type=int, default=0)
    
    args = parser.parse_args()
    
    try:
        if args.action == 'ask_info':
            ask_for_info(args.repo_name, args.pr_number, args.pr_author, args.github_token)
        
        elif args.action == 'assign_role':
            manager = DiscordManager(args.bot_token)
            manager.assign_role(args.guild_id, args.discord_user_id, args.role_id)
        
        elif args.action == 'remove_role':
            manager = DiscordManager(args.bot_token)
            manager.remove_role(args.guild_id, args.discord_user_id, args.role_id)
        
        elif args.action == 'post_success':
            post_success_message(args.repo_name, args.pr_number, args.pr_author,
                               args.github_token, args.message_type)
        
        # Add other actions as needed...
        
        print("✓ Discord operation completed successfully")
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

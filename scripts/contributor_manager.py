"""
Contributor Manager - Handle contributor registry operations.
"""

import argparse
import os
import sys
import subprocess
import tempfile
import shutil
import toml
from datetime import datetime
from typing import Dict, Any, Optional

sys.path.append(os.path.dirname(__file__))
from utils import load_config, sanitize_filename, calculate_lines_changed, write_output_file


class ContributorManager:
    """Manages contributor TOML files in GitHub Gist."""
    
    def __init__(self, gist_pat: str):
        if not gist_pat or gist_pat.strip() == '':
            raise ValueError("GIST_PAT is required")
        
        self.gist_pat = gist_pat
        self.config = load_config()
        self.gist_url = self.config['gist']['registry_url']
        self.repo_dir = None
    
    def clone_gist(self):
        """Clone Gist repository to temp directory."""
        self.repo_dir = os.path.join(tempfile.gettempdir(), 'contributor_gist_repo')
        
        # Fresh clone each time
        if os.path.exists(self.repo_dir):
            shutil.rmtree(self.repo_dir)
        
        # Clone with authentication
        auth_url = self.gist_url.replace('https://', f'https://{self.gist_pat}@')
        
        try:
            subprocess.run(
                ['git', 'clone', auth_url, self.repo_dir],
                check=True,
                capture_output=True,
                text=True
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to clone Gist: {e.stderr}")
    
    def contributor_exists(self, username: str) -> bool:
        """Check if contributor already exists in registry."""
        if not self.repo_dir:
            self.clone_gist()
        
        filename = self.config['gist']['contributor_file_pattern'].format(username=sanitize_filename(username))
        file_path = os.path.join(self.repo_dir, filename)
        
        return os.path.exists(file_path)
    
    def create_contributor(self, username: str, discord_id: str, wallet: str, pr_data: Dict[str, Any]) -> bool:
        """Create new contributor entry."""
        if not self.repo_dir:
            self.clone_gist()
        
        filename = self.config['gist']['contributor_file_pattern'].format(username=sanitize_filename(username))
        file_path = os.path.join(self.repo_dir, filename)
        
        # Create contributor data structure
        contributor_data = {
            'schema_version': self.config['gist']['schema_version'],
            'contributor': {
                'github_username': username,
                'discord_id': discord_id,
                'wallet_address': wallet,
                'total_prs': 1
            },
            'pull_requests': [
                {
                    'pr_number': pr_data['pr_number'],
                    'repository': pr_data['repo_name'],
                    'title': pr_data.get('pr_title', ''),
                    'lines_changed': pr_data.get('lines_changed', 0),
                    'labels': pr_data.get('labels', [])
                }
            ]
        }
        
        # Write TOML file
        with open(file_path, 'w') as f:
            toml.dump(contributor_data, f)
        
        # Commit and push
        try:
            subprocess.run(['git', '-C', self.repo_dir, 'add', filename], check=True)
            subprocess.run(
                ['git', '-C', self.repo_dir, 'commit', '-m', f'Add contributor: {username}'],
                check=True
            )
            subprocess.run(['git', '-C', self.repo_dir, 'push'], check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to commit/push: {e}")
            return False
    
    def add_pr_to_contributor(self, username: str, pr_data: Dict[str, Any]) -> bool:
        """Add new PR to existing contributor."""
        if not self.repo_dir:
            self.clone_gist()
        
        filename = self.config['gist']['contributor_file_pattern'].format(username=sanitize_filename(username))
        file_path = os.path.join(self.repo_dir, filename)
        
        if not os.path.exists(file_path):
            print(f"Contributor file not found: {filename}")
            return False
        
        # Load existing data
        with open(file_path, 'r') as f:
            contributor_data = toml.load(f)
        
        # Add new PR
        new_pr = {
            'pr_number': pr_data['pr_number'],
            'repository': pr_data['repo_name'],
            'title': pr_data.get('pr_title', ''),
            'lines_changed': pr_data.get('lines_changed', 0),
            'labels': pr_data.get('labels', [])
        }
        
        contributor_data['pull_requests'].append(new_pr)
        contributor_data['contributor']['total_prs'] = len(contributor_data['pull_requests'])
        
        # Write updated TOML
        with open(file_path, 'w') as f:
            toml.dump(contributor_data, f)
        
        # Commit and push
        try:
            subprocess.run(['git', '-C', self.repo_dir, 'add', filename], check=True)
            subprocess.run(
                ['git', '-C', self.repo_dir, 'commit', '-m', f'Update contributor: {username} (PR #{pr_data["pr_number"]})'],
                check=True
            )
            subprocess.run(['git', '-C', self.repo_dir, 'push'], check=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Failed to commit/push: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description='Contributor registry management')
    parser.add_argument('--action', required=True, 
                       choices=['check_exists', 'create', 'add_pr'])
    parser.add_argument('--username', help='GitHub username')
    parser.add_argument('--discord-id', help='Discord user ID')
    parser.add_argument('--wallet', help='Wallet address')
    parser.add_argument('--pr-number', type=int, help='PR number')
    parser.add_argument('--repo-name', help='Repository name')
    parser.add_argument('--pr-title', help='PR title')
    parser.add_argument('--lines-changed', type=int, default=0, help='Lines changed')
    parser.add_argument('--labels', help='PR labels (JSON array string)')
    parser.add_argument('--gist-pat', required=True, help='GitHub PAT for Gist')
    parser.add_argument('--output-file', help='Output file for results')
    
    args = parser.parse_args()
    
    try:
        manager = ContributorManager(args.gist_pat)
        
        if args.action == 'check_exists':
            exists = manager.contributor_exists(args.username)
            result = {'exists': exists, 'username': args.username}
            if args.output_file:
                write_output_file(result, args.output_file)
            print(f"Contributor exists: {exists}")
        
        elif args.action == 'create':
            import json
            labels = json.loads(args.labels) if args.labels else []
            
            pr_data = {
                'pr_number': args.pr_number,
                'repo_name': args.repo_name,
                'pr_title': args.pr_title or '',
                'lines_changed': args.lines_changed,
                'labels': labels
            }
            
            success = manager.create_contributor(args.username, args.discord_id, args.wallet, pr_data)
            if success:
                print(f"✓ Created contributor: {args.username}")
            else:
                print(f"✗ Failed to create contributor")      
                sys.exit(1)
        
        elif args.action == 'add_pr':
            import json
            labels = json.loads(args.labels) if args.labels else []
            
            pr_data = {
                'pr_number': args.pr_number,
                'repo_name': args.repo_name,
                'pr_title': args.pr_title or '',
                'lines_changed': args.lines_changed,
                'labels': labels
            }
            
            success = manager.add_pr_to_contributor(args.username, pr_data)
            if success:
                print(f"✓ Added PR to contributor: {args.username}")
            else:
                print(f"✗ Failed to add PR")
                sys.exit(1)
    
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()

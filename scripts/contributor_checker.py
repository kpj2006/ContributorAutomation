"""
Contributor checker - Check if contributor exists and their status.
"""

import argparse
import os
import sys
from typing import Dict, Any, Optional
from github import Github
import toml

# Import utilities
sys.path.append(os.path.dirname(__file__))
from utils import (
    load_config, load_error_messages, write_output_file,
    parse_discord_wallet_comment, sanitize_filename, validate_discord_id, validate_wallet_address
)


def clone_gist_repo(gist_pat: str, temp_dir: str) -> None:
    """
    Clone Gist repository to specified temp location.
    
    Args:
        gist_pat: GitHub Personal Access Token for Gist access
        temp_dir: Path to temporary directory for cloning
    
    Edge cases:
    - Git not available
    - Authentication failure
    """
    import subprocess
    
    config = load_config()
    gist_url = config['gist']['registry_url']
    
    # Clone with timeout
    auth_url = gist_url.replace('https://', f'https://{gist_pat}@')
    
    try:
        subprocess.run(['git', 'clone', auth_url, temp_dir], check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError:
        # Avoid leaking PAT in error message
        raise RuntimeError("Failed to clone gist repository") from None
    except subprocess.TimeoutExpired:
        raise RuntimeError("Git clone operation timed out") from None


def check_contributor_exists(pr_author: str, gist_pat: str) -> Dict[str, Any]:
    """
    Check if contributor TOML file exists in Gist.
    
    Edge cases:
    - Username case sensitivity
    - Special characters in username
    - Gist access failure
    
    Returns:
        Dict with 'exists' bool and 'toml_data' if exists
    """
    import tempfile
    
    try:
        print(f"Checking for contributor: {pr_author}")
        
        # Use context manager for automatic cleanup
        with tempfile.TemporaryDirectory(prefix='aossie_gist_repo_') as gist_dir:
            clone_gist_repo(gist_pat, gist_dir)
            print(f"Gist cloned to: {gist_dir}")
            
            config = load_config()
            filename_pattern = config['gist']['contributor_file_pattern']
            sanitized_username = sanitize_filename(pr_author)
            filename = filename_pattern.replace('{username}', sanitized_username)
            
            filepath = os.path.join(gist_dir, filename)
            print(f"Looking for file: {filepath}")
            print(f"File exists: {os.path.exists(filepath)}")
            
            # List files in gist directory for debugging
            if os.path.exists(gist_dir):
                files = os.listdir(gist_dir)
                print(f"Files in gist: {files[:10]}")  # Show first 10 files
            
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    toml_data = toml.load(f)
                
                return {
                    'exists': True,
                    'toml_data': toml_data,
                    'filepath': filepath
                }
            else:
                return {
                    'exists': False,
                    'filepath': filepath
                }
        # Temp directory is automatically cleaned up when exiting the context
    
    except Exception as e:
        error_msg = str(e)
        print(f"Error checking contributor: {error_msg}")
        # Note: Sensitive data should already be sanitized by clone_gist_repo
        return {
            'exists': False,
            'error': error_msg
        }


def check_for_response_in_pr(repo_name: str, pr_number: int, pr_author: str, github_token: str) -> Dict[str, Any]:
    """
    Check PR comments for Discord ID and wallet response.
    
    Edge cases:
    - Multiple comments by author
    - Edited comments
    - Invalid format responses
    - Comments by others (ignore)
    """
    try:
        g = Github(github_token)
        repo = g.get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        
        comments = pr.get_issue_comments()
        
        # Look for response from PR author
        for comment in reversed(list(comments)):  # Start with most recent
            if comment.user.login.lower() == pr_author.lower():
                parsed = parse_discord_wallet_comment(comment.body)
                
                if parsed:
                    # Validate
                    discord_valid = validate_discord_id(parsed.get('discord_id', ''))
                    wallet_valid = validate_wallet_address(parsed.get('wallet_address', ''))
                    
                    return {
                        'has_response': True,
                        'discord_id': parsed.get('discord_id', ''),
                        'wallet_address': parsed.get('wallet_address', ''),
                        'valid': discord_valid and wallet_valid,
                        'discord_valid': discord_valid,
                        'wallet_valid': wallet_valid,
                        'comment_id': comment.id
                    }
        
        return {
            'has_response': False
        }
    
    except Exception as e:
        print(f"Error checking PR comments: {e}")
        return {
            'has_response': False,
            'error': str(e)
        }


def check_promotion_eligibility(pr_author: str, gist_pat: str) -> Dict[str, Any]:
    """
    Check if contributor is eligible for Sentinel promotion.
    
    Criteria:
    - Has >= threshold successful PRs
    - Currently Apprentice role
    - Not blocked
    
    Edge cases:
    - Already Sentinel
    - Not onboarded yet
    - Blocked status
    """
    result = check_contributor_exists(pr_author, gist_pat)
    
    if not result['exists']:
        return {
            'exists': False,
            'eligible_for_promotion': False
        }
    
    toml_data = result['toml_data']
    config = load_config()
    threshold = config['promotion']['threshold']
    min_avg_lines = config['promotion']['min_avg_lines']
    
    # Get current stats
    current_role = toml_data.get('status', {}).get('current_role', 'Apprentice')
    is_blocked = toml_data.get('status', {}).get('blocked', False)
    total_prs = toml_data.get('stats', {}).get('total_prs', 0)
    avg_lines = toml_data.get('stats', {}).get('avg_lines_changed', 0)
    discord_id = toml_data.get('discord', {}).get('user_id', '')
    
    # Check eligibility
    eligible = (
        current_role == 'Apprentice' and
        not is_blocked and
        total_prs >= threshold and
        avg_lines >= min_avg_lines
    )
    
    return {
        'exists': True,
        'eligible_for_promotion': eligible,
        'current_role': current_role,
        'total_prs': total_prs,
        'avg_lines': avg_lines,
        'discord_id': discord_id,
        'is_blocked': is_blocked
    }


def main():
    parser = argparse.ArgumentParser(description='Check contributor status')
    parser.add_argument('--action', choices=['check_exists', 'check_response', 'check_promotion'], 
                       default='check_exists')
    parser.add_argument('--pr-author', help='PR author username')
    parser.add_argument('--repo-name', help='Repository name (owner/repo)')
    parser.add_argument('--pr-number', type=int, help='PR number')
    parser.add_argument('--gist-pat', help='Gist Personal Access Token')
    parser.add_argument('--github-token', help='GitHub token')
    parser.add_argument('--output-file', default='output.json', help='Output JSON file')
    
    args = parser.parse_args()
    
    # Validate required arguments for each action
    if args.action == 'check_exists':
        if not args.pr_author:
            parser.error("--pr-author is required for check_exists action")
        if not args.gist_pat:
            parser.error("--gist-pat is required for check_exists action")
    
    elif args.action == 'check_response':
        if not args.repo_name:
            parser.error("--repo-name is required for check_response action")
        if not args.pr_number:
            parser.error("--pr-number is required for check_response action")
        if not args.pr_author:
            parser.error("--pr-author is required for check_response action")
        if not args.github_token:
            parser.error("--github-token is required for check_response action")
    
    elif args.action == 'check_promotion':
        if not args.pr_author:
            parser.error("--pr-author is required for check_promotion action")
        if not args.gist_pat:
            parser.error("--gist-pat is required for check_promotion action")
    
    try:
        if args.action == 'check_exists':
            result = check_contributor_exists(args.pr_author, args.gist_pat)
        
        elif args.action == 'check_response':
            result = check_for_response_in_pr(args.repo_name, args.pr_number, 
                                             args.pr_author, args.github_token)
        
        elif args.action == 'check_promotion':
            result = check_promotion_eligibility(args.pr_author, args.gist_pat)
        
        write_output_file(args.output_file, result)
        print(f"Result written to {args.output_file}")
        
    except Exception as e:
        print(f"Error: {e}")
        write_output_file(args.output_file, {'error': str(e), 'success': False})
        sys.exit(1)


if __name__ == '__main__':
    main()

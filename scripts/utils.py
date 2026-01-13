"""
Utility functions for contributor automation.
"""

import os
import json
import toml
from typing import Dict, Any, Optional


def load_config() -> Dict[str, Any]:
    """Load configuration from config.toml."""
    config_path = os.path.join(os.path.dirname(__file__), '..', 'config', 'config.toml')
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    return toml.load(config_path)


def write_output_file(data: Dict[str, Any], output_file: str):
    """Write data to JSON output file."""
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)


def sanitize_filename(username: str) -> str:
    """
    Sanitize username for use in filename.
    Removes special characters and converts to lowercase.
    """
    # Remove special chars, keep alphanumeric, dash, underscore
    sanitized = ''.join(c for c in username if c.isalnum() or c in '-_')
    return sanitized.lower()


def validate_discord_id(discord_id: str) -> bool:
    """
    Basic Discord ID validation.
    Checks if it's numeric and within expected length range.
    """
    if not discord_id or not isinstance(discord_id, str):
        return False
    
    discord_id = discord_id.strip().strip('"').strip("'")
    
    if not discord_id.isdigit():
        return False
    
    config = load_config()
    min_len = config['onboarding']['discord_id_min_length']
    max_len = config['onboarding']['discord_id_max_length']
    
    return min_len <= len(discord_id) <= max_len


def validate_wallet_address(wallet: str) -> bool:
    """
    Basic Ethereum wallet validation.
    Checks format: 0x followed by 40 hex characters.
    """
    if not wallet or not isinstance(wallet, str):
        return False
    
    wallet = wallet.strip().strip('"').strip("'")
    
    config = load_config()
    prefix = config['onboarding']['wallet_prefix']
    length = config['onboarding']['wallet_length']
    
    if not wallet.lower().startswith(prefix):
        return False
    
    if len(wallet) != length:
        return False
    
    # Check if it's valid hex (after 0x)
    try:
        int(wallet[2:], 16)
        return True
    except ValueError:
        return False


def parse_contributor_comment(comment_body: str) -> Optional[Dict[str, str]]:
    """
    Parse Discord ID and wallet from contributor comment.
    
    Expected format:
    discord: "123456789012345678"
    wallet: "0x1234567890abcdef1234567890abcdef12345678"
    """
    import re
    
    discord_match = re.search(r'discord:\s*["\']?(\d{17,20})["\']?', comment_body, re.IGNORECASE)
    wallet_match = re.search(r'wallet:\s*["\']?(0x[a-fA-F0-9]{40})["\']?', comment_body, re.IGNORECASE)
    
    if not discord_match or not wallet_match:
        return None
    
    return {
        'discord_id': discord_match.group(1),
        'wallet': wallet_match.group(1)
    }


def calculate_lines_changed(pr_data: Any) -> int:
    """Calculate total lines changed (additions + deletions) in a PR."""
    additions = getattr(pr_data, 'additions', 0) or 0
    deletions = getattr(pr_data, 'deletions', 0) or 0
    return additions + deletions

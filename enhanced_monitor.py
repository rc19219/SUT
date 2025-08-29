#!/usr/bin/env python3
"""
Enhanced File Monitor with Before/After Pattern Comparison
Shows exact format requested: Yesterday's Patterns vs Today's Patterns
"""

import os
import time
import json
import hashlib
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Set
import requests
import glob
import re

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('enhanced_monitor.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class EnhancedFileMonitor:
    def __init__(self):
        # Configuration
        self.monitor_folders = ['clean_enhanced_la_finance_data_*', 'comparison_reports_*']
        self.check_interval = 3  # seconds - faster for testing
        self.teams_webhook_url = "https://ryantax.webhook.office.com/webhookb2/6016bcc3-2d37-4f26-942d-aa7587e6d7b8@a70caac2-dad6-4a68-8c0d-718e84a09c7e/IncomingWebhook/0534b61cb669401ab4cae1dce52b21d7/08fac451-5c84-4890-a9da-8f844c39a34d/V2UM7k2woLFcFTDboir2HiSDdFJodfPhBPgq0mH7oVJm81"
        
        # State tracking
        self.file_states: Dict[str, str] = {}  # file_path -> content_hash
        self.file_patterns: Dict[str, Dict] = {}  # file_path -> patterns (for before/after comparison)
        self.notified_changes: Set[str] = set()
        self.state_file = "enhanced_monitor_state.json"
        
        self.load_state()
        
        logger.info("ENHANCED FILE MONITOR STARTED")
        logger.info(f"Monitoring: {', '.join(self.monitor_folders)}")
        logger.info(f"Check every: {self.check_interval} seconds")
        logger.info("Features: Before/After Pattern Comparison")

    def load_state(self):
        """Load previous monitoring state"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    state_data = json.load(f)
                    self.file_states = state_data.get('file_states', {})
                    self.file_patterns = state_data.get('file_patterns', {})
                    self.notified_changes = set(state_data.get('notified_changes', []))
                logger.info(f"Loaded state: {len(self.file_states)} files tracked")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")

    def save_state(self):
        """Save current monitoring state"""
        try:
            state_data = {
                'file_states': self.file_states,
                'file_patterns': self.file_patterns,
                'notified_changes': list(self.notified_changes),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state_data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def get_file_hash(self, file_path: str) -> str:
        """Calculate MD5 hash of file content"""
        try:
            hash_md5 = hashlib.md5()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash file {file_path}: {e}")
            return ""

    def find_monitored_files(self) -> List[str]:
        """Find all files in monitored folders"""
        monitored_files = []
        for pattern in self.monitor_folders:
            folders = glob.glob(pattern)
            for folder in folders:
                if os.path.isdir(folder):
                    for root, dirs, files in os.walk(folder):
                        for file in files:
                            if file.endswith('.txt'):
                                file_path = os.path.join(root, file)
                                monitored_files.append(file_path)
        return monitored_files

    def analyze_file_patterns(self, file_path: str) -> Dict:
        """Analyze financial patterns in a file using the same logic as daily comparison reporter"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Extract the DETECTED PATTERNS section (same as daily comparison reporter)
            patterns_section = self.extract_patterns_section(content)
            if not patterns_section:
                return {}
            
            # Parse individual patterns from the section
            patterns_list = self.extract_individual_patterns(patterns_section)
            
            # Categorize patterns
            patterns = {
                'percentages': [],
                'dollar_amounts': [],
                'tax_terms': [],
                'dates': [],
                'all_patterns': patterns_list
            }
            
            for pattern in patterns_list:
                pattern = pattern.strip()
                if not pattern:
                    continue
                    
                # Check for percentages
                if pattern.endswith('%'):
                    patterns['percentages'].append(pattern)
                # Check for dollar amounts
                elif pattern.startswith('$'):
                    patterns['dollar_amounts'].append(pattern)
                # Check for tax terms
                elif any(term in pattern.lower() for term in ['tax', 'exemption', 'rate', 'relief', 'assessment', 'liability', 'registration']):
                    patterns['tax_terms'].append(pattern)
                # Check for dates
                elif '/' in pattern or '-' in pattern:
                    if any(char.isdigit() for char in pattern):
                        patterns['dates'].append(pattern)
            
            return patterns
            
        except Exception as e:
            logger.error(f"Error analyzing patterns in {file_path}: {e}")
            return {}

    def extract_patterns_section(self, text: str) -> str:
        """Extract only the DETECTED PATTERNS section from the file"""
        try:
            # Find the DETECTED PATTERNS section
            pattern_start = text.find("DETECTED PATTERNS:")
            if pattern_start == -1:
                return ""
            
            # Find the end of the patterns section
            pattern_end = text.find("------------------------------------------------------------", pattern_start + 1)
            if pattern_end == -1:
                pattern_end = text.find("CONTENT:", pattern_start)
            if pattern_end == -1:
                pattern_end = text.find("MARKDOWN CONTENT:", pattern_start)
            if pattern_end == -1:
                # If no clear end marker, take next 500 characters
                pattern_end = pattern_start + 500
            
            patterns_section = text[pattern_start:pattern_end].strip()
            return patterns_section
        except:
            return ""

    def extract_individual_patterns(self, patterns_section: str) -> List[str]:
        """Extract individual patterns from the DETECTED PATTERNS section"""
        if not patterns_section:
            return []
        
        # Remove the header and get actual patterns
        patterns_text = patterns_section.replace("DETECTED PATTERNS:", "").strip()
        
        # Split by comma and clean up
        patterns_list = []
        if patterns_text:
            raw_patterns = patterns_text.split(',')
            for pattern in raw_patterns:
                cleaned = pattern.strip()
                if cleaned and len(cleaned) > 0:
                    patterns_list.append(cleaned)
        
        return patterns_list

    def check_for_changes(self):
        """Check for file changes and return list of changes with pattern comparison"""
        current_files = self.find_monitored_files()
        current_file_set = set(current_files)
        previous_file_set = set(self.file_states.keys())
        
        changes = []
        
        # Check for new files
        new_files = current_file_set - previous_file_set
        for file_path in new_files:
            content_hash = self.get_file_hash(file_path)
            current_patterns = self.analyze_file_patterns(file_path)
            
            self.file_states[file_path] = content_hash
            self.file_patterns[file_path] = current_patterns
            
            change_id = f"new_{file_path}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            if change_id not in self.notified_changes:
                changes.append({
                    'type': 'NEW',
                    'file': os.path.basename(file_path),
                    'path': file_path,
                    'time': datetime.now().strftime('%H:%M:%S'),
                    'id': change_id,
                    'current_patterns': current_patterns
                })
                logger.info(f"NEW FILE: {os.path.basename(file_path)}")
        
        # Check for modified files (this is where the magic happens)
        for file_path in current_file_set & previous_file_set:
            current_hash = self.get_file_hash(file_path)
            previous_hash = self.file_states.get(file_path, "")
            
            if current_hash != previous_hash:
                # Get patterns for before/after comparison
                current_patterns = self.analyze_file_patterns(file_path)
                previous_patterns = self.file_patterns.get(file_path, {})
                
                # Update stored states
                self.file_states[file_path] = current_hash
                self.file_patterns[file_path] = current_patterns
                
                change_id = f"modified_{file_path}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                if change_id not in self.notified_changes:
                    changes.append({
                        'type': 'MODIFIED',
                        'file': os.path.basename(file_path),
                        'path': file_path,
                        'time': datetime.now().strftime('%H:%M:%S'),
                        'id': change_id,
                        'previous_patterns': previous_patterns,
                        'current_patterns': current_patterns
                    })
                    logger.info(f"MODIFIED: {os.path.basename(file_path)}")
        
        return changes

    def send_teams_notification(self, changes: List[Dict]):
        """Send Teams notification with before/after pattern comparison"""
        if not changes:
            return
        
        try:
            new_files = [c for c in changes if c['type'] == 'NEW']
            modified_files = [c for c in changes if c['type'] == 'MODIFIED']
            
            # Build message exactly like your requested format
            message = {
                "@type": "MessageCard",
                "@context": "https://schema.org/extensions",
                "summary": f"Financial Pattern Changes Detected - {len(changes)} changes",
                "themeColor": "0078D4",
                "sections": [
                    {
                        "activityTitle": "🔍 Financial Pattern Changes Detected",
                        "activitySubtitle": f"Daily Comparison: {(datetime.now() - timedelta(days=1)).strftime('%Y%m%d')} → {datetime.now().strftime('%Y%m%d')}",
                        "facts": [
                            {"name": "📅 Analysis Date", "value": datetime.now().strftime('%Y-%m-%d %H:%M:%S')},
                            {"name": "📁 WEB PAGES Analyzed", "value": str(len(self.file_states))},
                            {"name": "🔄 WEB PAGE with Changes", "value": str(len(modified_files))}
                        ]
                    }
                ]
            }
            
            # Add detailed before/after analysis for each modified file
            if modified_files:
                for change in modified_files[:3]:  # Show first 3 files
                    file_name = change['file']
                    previous_patterns = change.get('previous_patterns', {})
                    current_patterns = change.get('current_patterns', {})
                    
                    # Extract key patterns for display
                    old_display_patterns = []
                    new_display_patterns = []
                    
                    # Add percentages first
                    if previous_patterns.get('percentages'):
                        old_display_patterns.extend(previous_patterns['percentages'][:3])
                    if current_patterns.get('percentages'):
                        new_display_patterns.extend(current_patterns['percentages'][:3])
                        
                    # Add tax terms
                    if previous_patterns.get('tax_terms'):
                        old_display_patterns.extend([t.lower() for t in previous_patterns['tax_terms'][:3]])
                    if current_patterns.get('tax_terms'):
                        new_display_patterns.extend([t.lower() for t in current_patterns['tax_terms'][:3]])
                    
                    # Add dollar amounts
                    if previous_patterns.get('dollar_amounts'):
                        old_display_patterns.extend(previous_patterns['dollar_amounts'][:2])
                    if current_patterns.get('dollar_amounts'):
                        new_display_patterns.extend(current_patterns['dollar_amounts'][:2])
                    
                    # Build facts for this file
                    file_facts = [
                        {
                            "name": "Yesterday's Patterns",
                            "value": ', '.join(old_display_patterns[:8]) if old_display_patterns else "No patterns recorded"
                        },
                        {
                            "name": "Today's Patterns",
                            "value": ', '.join(new_display_patterns[:8]) if new_display_patterns else "No patterns found"
                        }
                    ]
                    
                    # Calculate key changes
                    key_changes = []
                    
                    # Compare percentages for direct replacements
                    old_pcts = set(previous_patterns.get('percentages', []))
                    new_pcts = set(current_patterns.get('percentages', []))
                    
                    # Look for simple 1-to-1 replacements (like 20% → 25%)
                    if len(old_pcts) == 1 and len(new_pcts) == 1 and old_pcts != new_pcts:
                        old_pct = list(old_pcts)[0]
                        new_pct = list(new_pcts)[0] 
                        key_changes.append(f"🔄 {old_pct} → {new_pct}")
                    else:
                        # Show additions and removals
                        added_pcts = new_pcts - old_pcts
                        removed_pcts = old_pcts - new_pcts
                        for pct in list(added_pcts)[:2]:
                            key_changes.append(f"➕ {pct} (new)")
                        for pct in list(removed_pcts)[:2]:
                            key_changes.append(f"➖ {pct} (removed)")
                    
                    # Compare dollar amounts
                    old_dollars = set(previous_patterns.get('dollar_amounts', []))
                    new_dollars = set(current_patterns.get('dollar_amounts', []))
                    
                    added_dollars = new_dollars - old_dollars
                    removed_dollars = old_dollars - new_dollars
                    
                    for amt in list(added_dollars)[:2]:
                        key_changes.append(f"➕ {amt} (new)")
                    for amt in list(removed_dollars)[:2]:
                        key_changes.append(f"➖ {amt} (removed)")
                    
                    # Add key changes to facts
                    file_facts.append({
                        "name": "Key Changes",
                        "value": '\\n'.join(key_changes) if key_changes else "No significant pattern changes detected"
                    })
                    
                    # Add webpage URL
                    webpage_url = "https://finance.lacity.gov/"
                    if 'forms-list' in file_name:
                        webpage_url = "https://finance.lacity.gov/forms-list"
                    
                    file_facts.append({
                        "name": "🌐 Webpage",
                        "value": webpage_url
                    })
                    
                    # Add file section
                    message["sections"].append({
                        "activityTitle": f"📄 {file_name}",
                        "facts": file_facts
                    })
            
            # Add new files if any
            if new_files:
                new_files_text = "\n".join([f"• {f['file']} ({f['time']})" for f in new_files[:5]])
                message["sections"].append({
                    "activityTitle": "📄 New Files Created",
                    "text": new_files_text
                })
            
            # Send notification
            response = requests.post(
                self.teams_webhook_url,
                json=message,
                headers={'Content-Type': 'application/json'},
                verify=False,
                timeout=10
            )
            
            if response.status_code == 200:
                for change in changes:
                    self.notified_changes.add(change['id'])
                logger.info(f"TEAMS NOTIFICATION SENT for {len(changes)} changes with before/after comparison")
            else:
                logger.error(f"Failed to send Teams notification: {response.status_code}")
                
        except Exception as e:
            logger.error(f"Error sending Teams notification: {e}")

    def monitor_continuously(self):
        """Main monitoring loop"""
        logger.info("Starting continuous monitoring with before/after pattern comparison...")
        
        try:
            while True:
                logger.info("Scanning for changes...")
                changes = self.check_for_changes()
                
                if changes:
                    logger.info(f"FOUND {len(changes)} CHANGES!")
                    self.send_teams_notification(changes)
                    self.save_state()
                else:
                    logger.info("No changes detected")
                
                logger.info(f"Next check in {self.check_interval} seconds...")
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
        finally:
            self.save_state()
            logger.info("Monitor shutdown complete")

def main():
    print("ENHANCED FILE MONITOR - Before/After Pattern Comparison")
    print("=" * 60)
    print("Mission: Show exact pattern changes like daily comparison")
    print("Format: Yesterday's Patterns vs Today's Patterns + Key Changes")
    print("Frequency: Check every 10 seconds")
    print("Stop: Press Ctrl+C")
    print("=" * 60)
    
    monitor = EnhancedFileMonitor()
    monitor.monitor_continuously()

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Daily Financial Data Comparison Reporter
- Compares financial data files between current day and previous day
- Generates detailed change reports focusing on detected patterns
- Creates interactive dashboards for change analysis
"""

import os
import glob
import json
import pandas as pd
import difflib
from datetime import datetime, timedelta
import re
from pathlib import Path
import hashlib
from typing import Dict, List, Tuple, Optional
import requests
import warnings
from urllib3.exceptions import InsecureRequestWarning
warnings.filterwarnings('ignore')
warnings.filterwarnings('ignore', category=InsecureRequestWarning)

class DailyComparisonReporter:
    def __init__(self, base_folder_pattern: str = "clean_enhanced_la_finance_data_*", teams_webhook_url: str = None):
        self.base_folder_pattern = base_folder_pattern
        self.current_date = datetime.now().strftime("%Y%m%d")
        self.previous_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        self.report_folder = f"comparison_reports_{self.current_date}"
        self.teams_webhook_url = "https://ryantax.webhook.office.com/webhookb2/6016bcc3-2d37-4f26-942d-aa7587e6d7b8@a70caac2-dad6-4a68-8c0d-718e84a09c7e/IncomingWebhook/0534b61cb669401ab4cae1dce52b21d7/08fac451-5c84-4890-a9da-8f844c39a34d/V2UM7k2woLFcFTDboir2HiSDdFJodfPhBPgq0mH7oVJm81"
        self.changes_summary = {
            'new_files': [],
            'deleted_files': [],
            'modified_files': [],
            'unchanged_files': [],
            'content_changes': {},
            'statistics': {}
        }
        
        # Create report directories
        os.makedirs(self.report_folder, exist_ok=True)
        os.makedirs(f"{self.report_folder}/visualizations", exist_ok=True)
        os.makedirs(f"{self.report_folder}/detailed_diffs", exist_ok=True)
        
        print(f"📊 Daily Comparison Reporter initialized")
        print(f"📅 Comparing: {self.previous_date} vs {self.current_date}")
        print(f"📁 Report folder: {self.report_folder}")

    def find_data_folders(self) -> Tuple[Optional[str], Optional[str]]:
        """Find current and previous day data folders"""
        current_folder = f"clean_enhanced_la_finance_data_{self.current_date}"
        previous_folder = f"clean_enhanced_la_finance_data_{self.previous_date}"
        
        current_path = current_folder if os.path.exists(current_folder) else None
        previous_path = previous_folder if os.path.exists(previous_folder) else None
        
        # If exact date folders don't exist, try to find the most recent ones
        if not current_path or not previous_path:
            all_folders = glob.glob(self.base_folder_pattern)
            all_folders.sort(reverse=True)  # Most recent first
            
            if len(all_folders) >= 2:
                current_path = all_folders[0] if not current_path else current_path
                previous_path = all_folders[1] if not previous_path else previous_path
            elif len(all_folders) == 1:
                current_path = all_folders[0] if not current_path else current_path
        
        return current_path, previous_path

    def get_file_hash(self, filepath: str) -> str:
        """Calculate hash of only the DETECTED PATTERNS section"""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            # Hash only the patterns section to ignore timestamps and formatting
            patterns_section = self.extract_financial_patterns_section(content)
            return hashlib.md5(patterns_section.encode()).hexdigest()
        except:
            return ""
    
    def extract_url_from_file(self, text: str) -> str:
        """Extract URL from the file header"""
        try:
            # Find URL line at the beginning of file
            lines = text.split('\n')
            for line in lines[:5]:  # Check first 5 lines
                if line.startswith("URL:"):
                    return line.replace("URL:", "").strip()
            return ""
        except:
            return ""

    def extract_financial_patterns_section(self, text: str) -> str:
        """Extract only the DETECTED PATTERNS section from the file"""
        try:
            # Find the DETECTED PATTERNS section
            pattern_start = text.find("DETECTED PATTERNS:")
            if pattern_start == -1:
                return ""
            
            # Find the end of the patterns section (next section or content start)
            pattern_end = text.find("------------------------------------------------------------", pattern_start + 1)
            if pattern_end == -1:
                pattern_end = text.find("CONTENT:", pattern_start)
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
        
        # Split by comma and clean each pattern
        patterns_list = [p.strip() for p in patterns_text.split(',') if p.strip()]
        
        return patterns_list

    def calculate_pattern_differences(self, old_patterns: List[str], new_patterns: List[str]) -> Dict:
        """Calculate specific differences between pattern lists accounting for duplicates"""
        from collections import Counter
        
        # Count occurrences of each pattern
        old_counts = Counter(old_patterns)
        new_counts = Counter(new_patterns)
        
        # Get all unique patterns
        all_patterns = set(old_patterns + new_patterns)
        
        # Track changes
        unchanged_patterns = []
        added_patterns = []
        removed_patterns = []
        modified_patterns = []
        
        # Check each unique pattern for changes in count
        for pattern in all_patterns:
            old_count = old_counts.get(pattern, 0)
            new_count = new_counts.get(pattern, 0)
            
            if old_count == new_count and old_count > 0:
                # Pattern count unchanged
                unchanged_patterns.extend([pattern] * old_count)
            elif old_count == 0 and new_count > 0:
                # Pattern newly added
                added_patterns.extend([pattern] * new_count)
            elif old_count > 0 and new_count == 0:
                # Pattern removed
                removed_patterns.extend([pattern] * old_count)
            elif old_count != new_count:
                # Pattern count changed - this might be a modification
                if new_count > old_count:
                    # More instances in new
                    unchanged_patterns.extend([pattern] * old_count)
                    added_patterns.extend([pattern] * (new_count - old_count))
                else:
                    # Fewer instances in new
                    unchanged_patterns.extend([pattern] * new_count)
                    removed_patterns.extend([pattern] * (old_count - new_count))
        
        # Now check for potential modifications between removed and added patterns
        remaining_removed = removed_patterns[:]
        remaining_added = added_patterns[:]
        
        for removed_pattern in removed_patterns[:]:
            for added_pattern in added_patterns[:]:
                if self.are_patterns_similar(removed_pattern, added_pattern):
                    modified_patterns.append({
                        'old': removed_pattern,
                        'new': added_pattern,
                        'change_type': 'modification'
                    })
                    if removed_pattern in remaining_removed:
                        remaining_removed.remove(removed_pattern)
                    if added_pattern in remaining_added:
                        remaining_added.remove(added_pattern)
                    break
        
        return {
            'unchanged': unchanged_patterns,
            'added': remaining_added,
            'removed': remaining_removed,
            'modified': modified_patterns,
            'total_old': len(old_patterns),
            'total_new': len(new_patterns)
        }

    def are_patterns_similar(self, pattern1: str, pattern2: str) -> bool:
        """Check if two patterns are similar enough to be considered modifications"""
        import re
        
        # Clean patterns for comparison
        p1 = pattern1.lower().strip()
        p2 = pattern2.lower().strip()
        
        # If patterns are identical, they're not modifications
        if p1 == p2:
            return False
        
        # Check for percentage patterns (e.g., 2023% vs 2024%)
        if p1.endswith('%') and p2.endswith('%'):
            return True
        
        # Check for dollar amount patterns (e.g., $1,200 vs $1,300)
        if p1.startswith('$') and p2.startswith('$'):
            return True
        
        # Check for year patterns (e.g., 2023 vs 2024)
        year_pattern = r'^\d{4}$'
        if re.match(year_pattern, p1) and re.match(year_pattern, p2):
            return True
        
        # General structure comparison (replace numbers with X)
        structure1 = re.sub(r'[\d.,]', 'X', p1)
        structure2 = re.sub(r'[\d.,]', 'X', p2)
        
        # If structures are the same but original patterns are different, it's likely a modification
        return structure1 == structure2 and p1 != p2

    def extract_financial_metrics(self, text: str) -> Dict:
        """Extract financial metrics from DETECTED PATTERNS section only"""
        # First extract only the patterns section
        patterns_section = self.extract_financial_patterns_section(text)
        
        if not patterns_section:
            return {
                'patterns_found': [],
                'patterns_count': 0,
                'unique_patterns': set(),
                'pattern_categories': {
                    'percentages': 0,
                    'dollar_amounts': 0,
                    'tax_assessments': 0,
                    'financial_terms': 0
                }
            }
        
        # Extract individual patterns from the section
        # Remove the header and get actual patterns
        patterns_text = patterns_section.replace("DETECTED PATTERNS:", "").strip()
        patterns_list = [p.strip() for p in patterns_text.split(',') if p.strip()]
        
        # Categorize patterns
        categories = {
            'percentages': 0,
            'dollar_amounts': 0, 
            'tax_assessments': 0,
            'financial_terms': 0
        }
        
        for pattern in patterns_list:
            pattern_lower = pattern.lower()
            if '%' in pattern:
                categories['percentages'] += 1
            elif '$' in pattern:
                categories['dollar_amounts'] += 1
            elif 'tax assessment' in pattern_lower:
                categories['tax_assessments'] += 1
            elif any(term in pattern_lower for term in ['tax', 'fee', 'rate', 'cost', 'liability']):
                categories['financial_terms'] += 1
        
        return {
            'patterns_found': patterns_list,
            'patterns_count': len(patterns_list),
            'unique_patterns': set(patterns_list),
            'pattern_categories': categories,
            'raw_patterns_section': patterns_section
        }

    def compare_files(self, current_folder: str, previous_folder: str) -> Dict:
        """Compare files between current and previous folders"""
        print("🔍 Analyzing file changes...")
        
        # Get all .txt files from both folders
        current_files = set(glob.glob(f"{current_folder}/*.txt"))
        previous_files = set(glob.glob(f"{previous_folder}/*.txt"))
        
        current_basenames = {os.path.basename(f) for f in current_files}
        previous_basenames = {os.path.basename(f) for f in previous_files}
        
        # Categorize changes
        new_files = current_basenames - previous_basenames
        deleted_files = previous_basenames - current_basenames
        common_files = current_basenames & previous_basenames
        
        modified_files = []
        unchanged_files = []
        content_changes = {}
        
        # Check for modifications in common files
        for filename in common_files:
            current_path = os.path.join(current_folder, filename)
            previous_path = os.path.join(previous_folder, filename)
            
            current_hash = self.get_file_hash(current_path)
            previous_hash = self.get_file_hash(previous_path)
            
            if current_hash != previous_hash:
                modified_files.append(filename)
                # Generate detailed diff
                content_changes[filename] = self.generate_detailed_diff(
                    previous_path, current_path, filename
                )
            else:
                unchanged_files.append(filename)
        
        self.changes_summary.update({
            'new_files': list(new_files),
            'deleted_files': list(deleted_files),
            'modified_files': modified_files,
            'unchanged_files': unchanged_files,
            'content_changes': content_changes,
            'statistics': {
                'total_current_files': len(current_files),
                'total_previous_files': len(previous_files),
                'new_files_count': len(new_files),
                'deleted_files_count': len(deleted_files),
                'modified_files_count': len(modified_files),
                'unchanged_files_count': len(unchanged_files)
            }
        })
        
        return self.changes_summary

    def generate_detailed_diff(self, old_file: str, new_file: str, filename: str) -> Dict:
        """Generate detailed diff analysis focusing only on financial patterns with individual pattern changes"""
        try:
            with open(old_file, 'r', encoding='utf-8') as f:
                old_content = f.read()
            with open(new_file, 'r', encoding='utf-8') as f:
                new_content = f.read()
            
            # Extract URL from the new file (current file)
            webpage_url = self.extract_url_from_file(new_content)
            
            # Extract only the financial patterns sections
            old_patterns = self.extract_financial_patterns_section(old_content)
            new_patterns = self.extract_financial_patterns_section(new_content)
            
            # Extract individual patterns as lists
            old_patterns_list = self.extract_individual_patterns(old_patterns)
            new_patterns_list = self.extract_individual_patterns(new_patterns)
            
            # Calculate specific pattern changes
            pattern_changes = self.calculate_pattern_differences(old_patterns_list, new_patterns_list)
            
            # Generate diff only for patterns sections
            old_lines = old_patterns.split('\n') if old_patterns else []
            new_lines = new_patterns.split('\n') if new_patterns else []
            
            diff = list(difflib.unified_diff(
                old_lines, new_lines,
                fromfile=f"Previous Day Patterns ({self.previous_date})",
                tofile=f"Current Day Patterns ({self.current_date})",
                lineterm=""
            ))
            
            # Save detailed diff to file
            diff_file = f"{self.report_folder}/detailed_diffs/{filename.replace('.txt', '_patterns_diff.txt')}"
            with open(diff_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(diff))
            
            # Extract metrics from patterns sections only
            old_metrics = self.extract_financial_metrics(old_content)
            new_metrics = self.extract_financial_metrics(new_content)
            
            # Add raw patterns section to metrics for comparison
            old_metrics['raw_patterns_section'] = old_patterns
            new_metrics['raw_patterns_section'] = new_patterns
            
            # Calculate meaningful changes including pattern modifications
            patterns_changed = old_patterns != new_patterns
            has_modifications = len(pattern_changes.get('modified', [])) > 0
            has_any_changes = patterns_changed or has_modifications
            patterns_added = len(new_metrics['patterns_found']) - len(old_metrics['patterns_found'])
            
            return {
                'diff_file': diff_file,
                'patterns_changed': has_any_changes,  # Use enhanced change detection
                'patterns_added': patterns_added,
                'old_metrics': old_metrics,
                'new_metrics': new_metrics,
                'metrics_comparison': self.compare_financial_patterns(old_metrics, new_metrics),
                'old_patterns_section': old_patterns,
                'new_patterns_section': new_patterns,
                'pattern_changes': pattern_changes,  # Add detailed pattern changes
                'webpage_url': webpage_url  # Add webpage URL
            }
            
        except Exception as e:
            print(f"⚠️  Error generating patterns diff for {filename}: {e}")
            return {'error': str(e)}

    def compare_financial_patterns(self, old_metrics: Dict, new_metrics: Dict) -> Dict:
        """Compare financial patterns between versions"""
        comparison = {}
        
        # Compare pattern categories
        for category in old_metrics['pattern_categories']:
            old_count = old_metrics['pattern_categories'][category]
            new_count = new_metrics['pattern_categories'][category]
            comparison[category] = {
                'old_count': old_count,
                'new_count': new_count,
                'change': new_count - old_count
            }
        
        # Compare overall patterns
        old_patterns = set(old_metrics['patterns_found'])
        new_patterns = set(new_metrics['patterns_found'])
        
        comparison['overall'] = {
            'old_total_patterns': old_metrics['patterns_count'],
            'new_total_patterns': new_metrics['patterns_count'],
            'total_change': new_metrics['patterns_count'] - old_metrics['patterns_count'],
            'patterns_added': list(new_patterns - old_patterns),
            'patterns_removed': list(old_patterns - new_patterns),
            'patterns_unchanged': list(old_patterns & new_patterns)
        }
        
        # Calculate significance of change
        patterns_changed = old_metrics.get('raw_patterns_section', '') != new_metrics.get('raw_patterns_section', '')
        comparison['change_significance'] = {
            'has_changes': patterns_changed,
            'added_count': len(comparison['overall']['patterns_added']),
            'removed_count': len(comparison['overall']['patterns_removed']),
            'net_change': comparison['overall']['total_change']
        }
        
        return comparison

    def format_pattern_modifications(self, modifications: List[Dict]) -> str:
        """Format pattern modifications for HTML display"""
        if not modifications:
            return '<em>No pattern modifications</em>'
        
        formatted_mods = []
        for mod in modifications:
            old_pattern = mod.get('old', '')
            new_pattern = mod.get('new', '')
            
            formatted_mod = f'''
            <div class="modified">
                <span class="pattern-item removed" style="display: inline;">{old_pattern}</span>
                <span class="modification-arrow">→</span>
                <span class="pattern-item added" style="display: inline;">{new_pattern}</span>
            </div>
            '''
            formatted_mods.append(formatted_mod)
        
        return ''.join(formatted_mods)

    def send_teams_notification(self, webhook_url: str, dashboard_url: str = None) -> bool:
        """Send Teams notification when financial pattern changes are detected"""
        try:
            # Check if there are any changes to report
            modified_files_with_changes = []
            for filename in self.changes_summary['modified_files']:
                if filename in self.changes_summary['content_changes']:
                    change_data = self.changes_summary['content_changes'][filename]
                    pattern_changes = change_data.get('pattern_changes', {})
                    if (pattern_changes.get('modified', []) or 
                        pattern_changes.get('added', []) or 
                        pattern_changes.get('removed', [])):
                        modified_files_with_changes.append(filename)
            
            if not modified_files_with_changes:
                print("📢 No significant financial pattern changes to notify about")
                return True
            
            # Build the Teams message
            message = self.build_teams_message(modified_files_with_changes, dashboard_url)
            
            # Send the message with SSL verification disabled for corporate environments
            headers = {'Content-Type': 'application/json'}
            response = requests.post(
                webhook_url, 
                json=message, 
                headers=headers,
                verify=False,  # Disable SSL verification for corporate environments
                timeout=10
            )
            
            if response.status_code == 200:
                print(f"✅ Teams notification sent successfully!")
                return True
            else:
                print(f"❌ Failed to send Teams notification: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            print(f"⚠️  Error sending Teams notification: {e}")
            return False

    def build_teams_message(self, modified_files: List[str], dashboard_url: str = None) -> Dict:
        """Build Microsoft Teams message with financial pattern changes"""
        
        # Create the main message card
        message = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": f"Financial Pattern Changes Detected - {self.current_date}",
            "themeColor": "0078D4",
            "sections": [
                {
                    "activityTitle": "🔍 Financial Pattern Changes Detected",
                    "activitySubtitle": f"Daily Comparison: {self.previous_date} → {self.current_date}",
                    "facts": [
                        {
                            "name": "📅 Analysis Date",
                            "value": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        },
                        {
                            "name": "📁 WEB PAGES Analyzed", 
                            "value": str(self.changes_summary['statistics']['total_current_files'])
                        },
                        {
                            "name": "🔄 WEB PAGE with Changes",
                            "value": str(len(modified_files))
                        }
                    ]
                }
            ]
        }
        
        # Add details for each modified file
        for filename in modified_files[:3]:  # Show max 3 files to avoid too long message
            change_data = self.changes_summary['content_changes'][filename]
            pattern_changes = change_data.get('pattern_changes', {})
            old_patterns = change_data.get('old_patterns_section', '')
            new_patterns = change_data.get('new_patterns_section', '')
            webpage_url = change_data.get('webpage_url', '')
            
            # Build change summary
            changes_text = []
            if pattern_changes.get('modified', []):
                for mod in pattern_changes['modified'][:2]:  # Show max 2 modifications per file
                    changes_text.append(f"🔄 **{mod['old']}** → **{mod['new']}**")
            
            if pattern_changes.get('added', []):
                for pattern in pattern_changes['added'][:2]:
                    changes_text.append(f"➕ **{pattern}** (new)")
            
            if pattern_changes.get('removed', []):
                for pattern in pattern_changes['removed'][:2]:
                    changes_text.append(f"➖ **{pattern}** (removed)")
            
            # Build facts list
            facts = [
                {
                    "name": "Yesterday's Patterns",
                    "value": old_patterns.replace("DETECTED PATTERNS:", "").strip()[:200] + ("..." if len(old_patterns) > 200 else "")
                },
                {
                    "name": "Today's Patterns", 
                    "value": new_patterns.replace("DETECTED PATTERNS:", "").strip()[:200] + ("..." if len(new_patterns) > 200 else "")
                },
                {
                    "name": "Key Changes",
                    "value": "\\n".join(changes_text[:3]) if changes_text else "Pattern content modified"
                }
            ]
            
            # Add webpage URL if available
            if webpage_url:
                facts.append({
                    "name": "🌐 Webpage",
                    "value": webpage_url
                })
            
            # Add file section
            file_section = {
                "activityTitle": f"📄 {filename}",
                "facts": facts
            }
            
            message["sections"].append(file_section)
        
        # Add actions
        actions = []
        
        if dashboard_url:
            actions.append({
                "@type": "OpenUri",
                "name": "🎯 View Dashboard",
                "targets": [{"os": "default", "uri": dashboard_url}]
            })
        
        # Add webpage links for changed files
        webpage_urls = []
        for filename in modified_files[:3]:  # Max 3 to avoid too many actions
            change_data = self.changes_summary['content_changes'][filename]
            webpage_url = change_data.get('webpage_url', '')
            if webpage_url and webpage_url not in webpage_urls:
                webpage_urls.append(webpage_url)
                actions.append({
                    "@type": "OpenUri",
                    "name": f"🌐 View {filename.replace('.txt', '').replace('-', ' ').title()}",
                    "targets": [{"os": "default", "uri": webpage_url}]
                })
        
        # Add local file action
        report_path = os.path.abspath(self.report_folder)
        actions.append({
            "@type": "OpenUri", 
            "name": "📁 Open Report Folder",
            "targets": [{"os": "default", "uri": f"file:///{report_path.replace(os.sep, '/')}"}]
        })
        
        if actions:
            message["potentialAction"] = actions
            
        return message

    def generate_individual_file_html(self, filename: str, change_data: Dict) -> str:
        """Generate comprehensive HTML report for individual file with differences only"""
        metrics = change_data.get('metrics_comparison', {})
        overall = metrics.get('overall', {})
        significance = metrics.get('change_significance', {})
        
        # Get old and new patterns sections
        old_patterns = change_data.get('old_patterns_section', '')
        new_patterns = change_data.get('new_patterns_section', '')
        
        # Create difference display
        patterns_added = overall.get('patterns_added', [])
        patterns_removed = overall.get('patterns_removed', [])
        patterns_unchanged = overall.get('patterns_unchanged', [])
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Financial Pattern Analysis - {filename}</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f8f9fa;
                    line-height: 1.6;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 30px;
                    border-radius: 15px;
                    box-shadow: 0 4px 20px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #2c3e50;
                    text-align: center;
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 15px;
                    margin-bottom: 30px;
                }}
                h2 {{
                    color: #34495e;
                    margin-top: 35px;
                    margin-bottom: 20px;
                    padding: 10px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    border-radius: 8px;
                }}
                h3 {{
                    color: #2980b9;
                    margin-top: 25px;
                    border-left: 4px solid #3498db;
                    padding-left: 15px;
                }}
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }}
                .stat-box {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                }}
                .stat-number {{
                    font-size: 2em;
                    font-weight: bold;
                    margin-bottom: 5px;
                }}
                .patterns-section {{
                    background-color: #ecf0f1;
                    padding: 20px;
                    border-radius: 10px;
                    margin: 15px 0;
                    border-left: 5px solid #3498db;
                }}
                .patterns-comparison {{
                    display: grid;
                    grid-template-columns: 1fr 1fr;
                    gap: 20px;
                    margin: 20px 0;
                }}
                .pattern-column {{
                    background: white;
                    padding: 20px;
                    border-radius: 10px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .pattern-item {{
                    padding: 8px 12px;
                    margin: 5px 0;
                    border-radius: 5px;
                    display: inline-block;
                    margin-right: 10px;
                }}
                .added {{ 
                    background-color: #d4edda; 
                    color: #155724; 
                    border: 1px solid #c3e6cb;
                }}
                .removed {{ 
                    background-color: #f8d7da; 
                    color: #721c24; 
                    border: 1px solid #f5c6cb;
                }}
                .unchanged {{ 
                    background-color: #e2e3e5; 
                    color: #383d41; 
                    border: 1px solid #d1d1d1;
                }}
                .modified {{
                    background-color: #fff3cd;
                    color: #856404;
                    border: 1px solid #ffeaa7;
                    margin: 5px 0;
                    padding: 10px;
                    border-radius: 8px;
                    display: block;
                }}
                .modification-arrow {{
                    color: #e17055;
                    font-weight: bold;
                    margin: 0 10px;
                }}
                .differences-section {{
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    color: white;
                    padding: 25px;
                    border-radius: 15px;
                    margin: 25px 0;
                }}
                .difference-item {{
                    background: rgba(255,255,255,0.1);
                    padding: 15px;
                    border-radius: 8px;
                    margin: 10px 0;
                    backdrop-filter: blur(10px);
                }}
                .no-changes {{
                    text-align: center;
                    color: #7f8c8d;
                    font-style: italic;
                    padding: 20px;
                    background-color: #ecf0f1;
                    border-radius: 10px;
                }}
                .timestamp {{
                    text-align: right;
                    color: #7f8c8d;
                    font-style: italic;
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #ecf0f1;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📊 Financial Pattern Analysis</h1>
                <p style="text-align: center; font-size: 1.3em; color: #7f8c8d;">
                    File: <strong>{filename}</strong><br>
                    Analysis Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                </p>
                
                <h2>📈 Summary Statistics</h2>
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-number">{overall.get('old_total_patterns', 0)}</div>
                        <div>Previous Day Patterns</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{overall.get('new_total_patterns', 0)}</div>
                        <div>Current Day Patterns</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{significance.get('added_count', 0)}</div>
                        <div>Patterns Added</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{significance.get('removed_count', 0)}</div>
                        <div>Patterns Removed</div>
                    </div>
                </div>
        """
        
        # Get detailed pattern changes
        pattern_changes = change_data.get('pattern_changes', {})
        
        # Add differences section if there are changes
        if significance.get('has_changes', False) or pattern_changes.get('modified', []):
            html_content += f"""
                <div class="differences-section">
                    <h2 style="margin-top: 0; background: none; color: white; padding: 0;">🔍 Financial Pattern Differences Detected</h2>
                    
                    {f'''
                    <div class="difference-item">
                        <h3 style="color: white; border-left: 4px solid white; margin: 0 0 15px 0;">🔄 Pattern Modifications ({len(pattern_changes.get('modified', []))})</h3>
                        <div>
                            {self.format_pattern_modifications(pattern_changes.get('modified', []))}
                        </div>
                    </div>
                    ''' if pattern_changes.get('modified', []) else ''}
                    
                    {f'''
                    <div class="difference-item">
                        <h3 style="color: white; border-left: 4px solid white; margin: 0 0 15px 0;">➕ New Patterns Added ({len(pattern_changes.get('added', []))})</h3>
                        <div>
                            {', '.join([f'<span class="pattern-item added">{pattern}</span>' for pattern in pattern_changes.get('added', [])]) if pattern_changes.get('added', []) else '<em>No new patterns added</em>'}
                        </div>
                    </div>
                    ''' if pattern_changes.get('added', []) else ''}
                    
                    {f'''
                    <div class="difference-item">
                        <h3 style="color: white; border-left: 4px solid white; margin: 0 0 15px 0;">➖ Patterns Removed ({len(pattern_changes.get('removed', []))})</h3>
                        <div>
                            {', '.join([f'<span class="pattern-item removed">{pattern}</span>' for pattern in pattern_changes.get('removed', [])]) if pattern_changes.get('removed', []) else '<em>No patterns removed</em>'}
                        </div>
                    </div>
                    ''' if pattern_changes.get('removed', []) else ''}
                    
                    <div class="difference-item">
                        <h3 style="color: white; border-left: 4px solid white; margin: 0 0 15px 0;">� Change Summary</h3>
                        <div style="font-size: 1.1em;">
                            <strong>Previous Day:</strong> {pattern_changes.get('total_old', 0)} patterns<br>
                            <strong>Current Day:</strong> {pattern_changes.get('total_new', 0)} patterns<br>
                            <strong>Net Change:</strong> {'+' if (pattern_changes.get('total_new', 0) - pattern_changes.get('total_old', 0)) > 0 else ''}{pattern_changes.get('total_new', 0) - pattern_changes.get('total_old', 0)} patterns
                        </div>
                    </div>
                </div>
            """
        else:
            html_content += """
                <div class="no-changes">
                    <h3>✅ No Financial Pattern Changes Detected</h3>
                    <p>The financial patterns in this file remained the same between the two comparison dates.</p>
                </div>
            """
        
        # Add patterns comparison section
        html_content += f"""
                <h2>📋 Pattern Details Comparison</h2>
                <div class="patterns-comparison">
                    <div class="pattern-column">
                        <h3>Previous Day Patterns ({self.previous_date})</h3>
                        <div class="patterns-section">
                            {old_patterns.replace('\n', '<br>') if old_patterns else '<em>No patterns detected</em>'}
                        </div>
                    </div>
                    <div class="pattern-column">
                        <h3>Current Day Patterns ({self.current_date})</h3>
                        <div class="patterns-section">
                            {new_patterns.replace('\n', '<br>') if new_patterns else '<em>No patterns detected</em>'}
                        </div>
                    </div>
                </div>
                
                {f'''
                <h2>🔄 Unchanged Patterns ({len(patterns_unchanged)})</h2>
                <div class="patterns-section">
                    {', '.join([f'<span class="pattern-item unchanged">{pattern}</span>' for pattern in patterns_unchanged]) if patterns_unchanged else '<em>No unchanged patterns</em>'}
                </div>
                ''' if patterns_unchanged else ''}
                
                <div class="timestamp">
                    Report generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}<br>
                    Comparison: {self.previous_date} → {self.current_date}
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content

    def generate_centralized_dashboard(self):
        """Generate a centralized dashboard with links to all analysis pages"""
        
        # Collect analysis links
        analysis_links = []
        for filename in self.changes_summary['modified_files']:
            if filename in self.changes_summary['content_changes']:
                safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename.replace('.txt', ''))
                analysis_file = f"visualizations/{safe_filename}_analysis.html"
                change_data = self.changes_summary['content_changes'][filename]
                metrics = change_data.get('metrics_comparison', {})
                significance = metrics.get('change_significance', {})
                
                analysis_links.append({
                    'filename': filename,
                    'safe_filename': safe_filename,
                    'analysis_file': analysis_file,
                    'has_changes': significance.get('has_changes', False),
                    'net_change': significance.get('net_change', 0),
                    'added_count': significance.get('added_count', 0),
                    'removed_count': significance.get('removed_count', 0)
                })
        
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Financial Data Analysis Dashboard - {self.current_date}</title>
            <style>
                * {{
                    margin: 0;
                    padding: 0;
                    box-sizing: border-box;
                }}
                
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    min-height: 100vh;
                    padding: 20px;
                }}
                
                .dashboard-container {{
                    max-width: 1400px;
                    margin: 0 auto;
                    background: rgba(255, 255, 255, 0.95);
                    border-radius: 20px;
                    backdrop-filter: blur(10px);
                    box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                    overflow: hidden;
                }}
                
                .dashboard-header {{
                    background: linear-gradient(135deg, #2c3e50 0%, #34495e 100%);
                    color: white;
                    padding: 40px;
                    text-align: center;
                }}
                
                .dashboard-title {{
                    font-size: 3em;
                    font-weight: 300;
                    margin-bottom: 15px;
                    text-shadow: 0 2px 10px rgba(0,0,0,0.3);
                }}
                
                .dashboard-subtitle {{
                    font-size: 1.2em;
                    opacity: 0.9;
                    margin-bottom: 10px;
                }}
                
                .comparison-dates {{
                    font-size: 1.1em;
                    opacity: 0.8;
                    margin-top: 15px;
                    padding: 10px 20px;
                    background: rgba(255,255,255,0.1);
                    border-radius: 25px;
                    display: inline-block;
                }}
                
                .dashboard-content {{
                    padding: 40px;
                }}
                
                .stats-overview {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                    gap: 25px;
                    margin-bottom: 40px;
                }}
                
                .stat-card {{
                    background: white;
                    padding: 30px;
                    border-radius: 15px;
                    text-align: center;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    transition: transform 0.3s ease, box-shadow 0.3s ease;
                    border-left: 5px solid;
                }}
                
                .stat-card:hover {{
                    transform: translateY(-5px);
                    box-shadow: 0 15px 40px rgba(0,0,0,0.15);
                }}
                
                .stat-card.total {{ border-left-color: #3498db; }}
                .stat-card.new {{ border-left-color: #27ae60; }}
                .stat-card.modified {{ border-left-color: #f39c12; }}
                .stat-card.deleted {{ border-left-color: #e74c3c; }}
                
                .stat-number {{
                    font-size: 2.5em;
                    font-weight: bold;
                    margin-bottom: 10px;
                }}
                
                .stat-label {{
                    font-size: 1.1em;
                    color: #7f8c8d;
                    text-transform: uppercase;
                    letter-spacing: 1px;
                }}
                
                .analysis-section {{
                    margin-top: 50px;
                }}
                
                .section-title {{
                    font-size: 2.2em;
                    color: #2c3e50;
                    margin-bottom: 30px;
                    text-align: center;
                    position: relative;
                }}
                
                .section-title::after {{
                    content: '';
                    position: absolute;
                    bottom: -10px;
                    left: 50%;
                    transform: translateX(-50%);
                    width: 100px;
                    height: 4px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    border-radius: 2px;
                }}
                
                .analysis-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
                    gap: 30px;
                    margin-top: 40px;
                }}
                
                .analysis-card {{
                    background: white;
                    border-radius: 15px;
                    overflow: hidden;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                    transition: all 0.3s ease;
                    border: 2px solid transparent;
                }}
                
                .analysis-card:hover {{
                    transform: translateY(-8px);
                    box-shadow: 0 20px 50px rgba(0,0,0,0.15);
                    border-color: #667eea;
                }}
                
                .card-header {{
                    padding: 25px;
                    background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
                    color: white;
                }}
                
                .card-title {{
                    font-size: 1.3em;
                    font-weight: 600;
                    margin-bottom: 10px;
                    word-break: break-word;
                }}
                
                .card-meta {{
                    opacity: 0.9;
                    font-size: 0.95em;
                }}
                
                .card-body {{
                    padding: 25px;
                }}
                
                .change-indicators {{
                    display: flex;
                    justify-content: space-around;
                    margin-bottom: 25px;
                }}
                
                .indicator {{
                    text-align: center;
                    padding: 15px;
                    border-radius: 10px;
                    min-width: 80px;
                }}
                
                .indicator.positive {{
                    background: #d4edda;
                    color: #155724;
                    border: 2px solid #c3e6cb;
                }}
                
                .indicator.negative {{
                    background: #f8d7da;
                    color: #721c24;
                    border: 2px solid #f5c6cb;
                }}
                
                .indicator.neutral {{
                    background: #e2e3e5;
                    color: #383d41;
                    border: 2px solid #d1d1d1;
                }}
                
                .indicator-number {{
                    font-size: 1.8em;
                    font-weight: bold;
                    margin-bottom: 5px;
                }}
                
                .indicator-label {{
                    font-size: 0.85em;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                
                .view-analysis-btn {{
                    display: block;
                    width: 100%;
                    padding: 15px;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    text-decoration: none;
                    border-radius: 10px;
                    text-align: center;
                    font-weight: 600;
                    font-size: 1.1em;
                    transition: all 0.3s ease;
                    border: none;
                    cursor: pointer;
                }}
                
                .view-analysis-btn:hover {{
                    background: linear-gradient(135deg, #5a67d8 0%, #667eea 100%);
                    transform: translateY(-2px);
                    box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4);
                }}
                
                .no-changes {{
                    text-align: center;
                    padding: 60px 40px;
                    color: #7f8c8d;
                    font-size: 1.2em;
                }}
                
                .no-changes-icon {{
                    font-size: 4em;
                    margin-bottom: 20px;
                    opacity: 0.5;
                }}
                
                .quick-links {{
                    background: white;
                    padding: 30px;
                    border-radius: 15px;
                    margin-top: 40px;
                    box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                }}
                
                .quick-links h3 {{
                    color: #2c3e50;
                    margin-bottom: 20px;
                    font-size: 1.5em;
                }}
                
                .links-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                }}
                
                .quick-link {{
                    padding: 15px 20px;
                    background: #f8f9fa;
                    border-radius: 8px;
                    text-decoration: none;
                    color: #2c3e50;
                    transition: all 0.3s ease;
                    border-left: 4px solid #3498db;
                }}
                
                .quick-link:hover {{
                    background: #e9ecef;
                    transform: translateX(5px);
                }}
                
                .footer {{
                    text-align: center;
                    padding: 30px;
                    color: #7f8c8d;
                    border-top: 1px solid #ecf0f1;
                    margin-top: 50px;
                }}
                
                @media (max-width: 768px) {{
                    .dashboard-title {{ font-size: 2em; }}
                    .analysis-grid {{ grid-template-columns: 1fr; }}
                    .stats-overview {{ grid-template-columns: repeat(2, 1fr); }}
                }}
            </style>
        </head>
        <body>
            <div class="dashboard-container">
                <div class="dashboard-header">
                    <h1 class="dashboard-title">📊 Financial Data Analysis Dashboard</h1>
                    <p class="dashboard-subtitle">Comprehensive Financial Pattern Comparison & Analysis</p>
                    <div class="comparison-dates">
                        📅 Comparing: {self.previous_date} ➜ {self.current_date}
                    </div>
                </div>
                
                <div class="dashboard-content">
                    <div class="stats-overview">
                        <div class="stat-card total">
                            <div class="stat-number">{self.changes_summary['statistics']['total_current_files']}</div>
                            <div class="stat-label">Total Files</div>
                        </div>
                        <div class="stat-card new">
                            <div class="stat-number">{self.changes_summary['statistics']['new_files_count']}</div>
                            <div class="stat-label">New Files</div>
                        </div>
                        <div class="stat-card modified">
                            <div class="stat-number">{self.changes_summary['statistics']['modified_files_count']}</div>
                            <div class="stat-label">Modified Files</div>
                        </div>
                        <div class="stat-card deleted">
                            <div class="stat-number">{self.changes_summary['statistics']['deleted_files_count']}</div>
                            <div class="stat-label">Deleted Files</div>
                        </div>
                    </div>
        """
        
        # Add analysis cards section
        if analysis_links:
            html_content += f"""
                    <div class="analysis-section">
                        <h2 class="section-title">🔍 File Analysis Reports</h2>
                        <div class="analysis-grid">
            """
            
            for link in analysis_links:
                change_status = "positive" if link['net_change'] > 0 else "negative" if link['net_change'] < 0 else "neutral"
                
                html_content += f"""
                            <div class="analysis-card">
                                <div class="card-header">
                                    <div class="card-title">📄 {link['filename']}</div>
                                    <div class="card-meta">
                                        {'✅ Changes Detected' if link['has_changes'] else '⚪ No Changes'}
                                    </div>
                                </div>
                                <div class="card-body">
                                    <div class="change-indicators">
                                        <div class="indicator positive">
                                            <div class="indicator-number">+{link['added_count']}</div>
                                            <div class="indicator-label">Added</div>
                                        </div>
                                        <div class="indicator negative">
                                            <div class="indicator-number">-{link['removed_count']}</div>
                                            <div class="indicator-label">Removed</div>
                                        </div>
                                        <div class="indicator {change_status}">
                                            <div class="indicator-number">{'+' if link['net_change'] > 0 else ''}{link['net_change']}</div>
                                            <div class="indicator-label">Net Change</div>
                                        </div>
                                    </div>
                                    <a href="{link['analysis_file']}" class="view-analysis-btn" target="_blank">
                                        🔍 View Detailed Analysis
                                    </a>
                                </div>
                            </div>
                """
            
            html_content += """
                        </div>
                    </div>
            """
        else:
            html_content += """
                    <div class="no-changes">
                        <div class="no-changes-icon">📊</div>
                        <h3>No Financial Pattern Changes Detected</h3>
                        <p>All financial patterns remained consistent between the comparison dates.</p>
                    </div>
            """
        
        # Add quick links section
        html_content += f"""
                    <div class="quick-links">
                        <h3>📋 Quick Access Links</h3>
                        <div class="links-grid">
                            <a href="visualizations/overview_dashboard.html" class="quick-link" target="_blank">
                                📊 Overview Dashboard
                            </a>
                            <a href="daily_comparison_report_{self.current_date}.html" class="quick-link" target="_blank">
                                📄 Full HTML Report
                            </a>
                            <a href="detailed_diffs/" class="quick-link" target="_blank">
                                🔍 Detailed Differences
                            </a>
                        </div>
                    </div>
                </div>
                
                <div class="footer">
                    <p>Financial Data Analysis Dashboard | Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
                    <p>Automated comparison system for financial pattern detection and analysis</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Save centralized dashboard
        dashboard_file = f"{self.report_folder}/financial_analysis_dashboard.html"
        with open(dashboard_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"🎯 Centralized dashboard created: {dashboard_file}")
        return dashboard_file

    def generate_html_report(self):
        """Generate comprehensive HTML report"""
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Daily Financial Patterns Comparison Report - {self.current_date}</title>
            <style>
                body {{
                    font-family: 'Arial', sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 0 20px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #2c3e50;
                    text-align: center;
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #34495e;
                    margin-top: 30px;
                }}
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }}
                .stat-box {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                }}
                .stat-number {{
                    font-size: 2em;
                    font-weight: bold;
                    margin-bottom: 5px;
                }}
                .file-list {{
                    background-color: #ecf0f1;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 10px 0;
                }}
                .file-item {{
                    padding: 5px 0;
                    border-bottom: 1px solid #bdc3c7;
                }}
                .new {{ color: #27ae60; }}
                .deleted {{ color: #e74c3c; }}
                .modified {{ color: #f39c12; }}
                .unchanged {{ color: #95a5a6; }}
                .timestamp {{
                    text-align: right;
                    color: #7f8c8d;
                    font-style: italic;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📊 Daily Financial Patterns Comparison Report</h1>
                <p style="text-align: center; font-size: 1.2em; color: #7f8c8d;">
                    Comparing financial patterns from {self.previous_date} to {self.current_date}
                </p>
                
                <h2>📈 Summary Statistics</h2>
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-number">{self.changes_summary['statistics']['total_current_files']}</div>
                        <div>Current Files</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{self.changes_summary['statistics']['new_files_count']}</div>
                        <div>New Files</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{self.changes_summary['statistics']['modified_files_count']}</div>
                        <div>Modified Files</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{self.changes_summary['statistics']['deleted_files_count']}</div>
                        <div>Deleted Files</div>
                    </div>
                </div>
        """
        
        # Add sections for each change type
        if self.changes_summary['new_files']:
            html_content += f"""
                <h2 class="new">🆕 New Files ({len(self.changes_summary['new_files'])})</h2>
                <div class="file-list">
                    {''.join([f'<div class="file-item new">✅ {file}</div>' for file in self.changes_summary['new_files']])}
                </div>
            """
        
        if self.changes_summary['modified_files']:
            html_content += f"""
                <h2 class="modified">🔄 Modified Files ({len(self.changes_summary['modified_files'])})</h2>
                <div class="file-list">
                    {''.join([f'<div class="file-item modified">📝 {file}</div>' for file in self.changes_summary['modified_files']])}
                </div>
            """
        
        if self.changes_summary['deleted_files']:
            html_content += f"""
                <h2 class="deleted">🗑️ Deleted Files ({len(self.changes_summary['deleted_files'])})</h2>
                <div class="file-list">
                    {''.join([f'<div class="file-item deleted">❌ {file}</div>' for file in self.changes_summary['deleted_files']])}
                </div>
            """
        
        html_content += f"""
                <h2>📊 Interactive Visualizations</h2>
                <ul>
                    <li><a href="financial_analysis_dashboard.html">🎯 Main Analysis Dashboard</a></li>
                    <li><a href="visualizations/overview_dashboard.html">Overview Dashboard</a></li>
                    <li>Individual financial pattern analyses available in visualizations folder</li>
                </ul>
                
                <div class="timestamp">
                    Report generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                </div>
            </div>
        </body>
        </html>
        """
        
        # Save HTML report
        html_file = f"{self.report_folder}/daily_comparison_report_{self.current_date}.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"📊 HTML report saved: {html_file}")
        """Generate comprehensive HTML report"""
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Daily Financial Patterns Comparison Report - {self.current_date}</title>
            <style>
                body {{
                    font-family: 'Arial', sans-serif;
                    margin: 0;
                    padding: 20px;
                    background-color: #f5f5f5;
                }}
                .container {{
                    max-width: 1200px;
                    margin: 0 auto;
                    background-color: white;
                    padding: 30px;
                    border-radius: 10px;
                    box-shadow: 0 0 20px rgba(0,0,0,0.1);
                }}
                h1 {{
                    color: #2c3e50;
                    text-align: center;
                    border-bottom: 3px solid #3498db;
                    padding-bottom: 10px;
                }}
                h2 {{
                    color: #34495e;
                    margin-top: 30px;
                }}
                .stats-grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 20px;
                    margin: 20px 0;
                }}
                .stat-box {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 20px;
                    border-radius: 10px;
                    text-align: center;
                }}
                .stat-number {{
                    font-size: 2em;
                    font-weight: bold;
                    margin-bottom: 5px;
                }}
                .file-list {{
                    background-color: #ecf0f1;
                    padding: 15px;
                    border-radius: 5px;
                    margin: 10px 0;
                }}
                .file-item {{
                    padding: 5px 0;
                    border-bottom: 1px solid #bdc3c7;
                }}
                .new {{ color: #27ae60; }}
                .deleted {{ color: #e74c3c; }}
                .modified {{ color: #f39c12; }}
                .unchanged {{ color: #95a5a6; }}
                .timestamp {{
                    text-align: right;
                    color: #7f8c8d;
                    font-style: italic;
                    margin-top: 20px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>📊 Daily Financial Patterns Comparison Report</h1>
                <p style="text-align: center; font-size: 1.2em; color: #7f8c8d;">
                    Comparing financial patterns from {self.previous_date} to {self.current_date}
                </p>
                
                <h2>📈 Summary Statistics</h2>
                <div class="stats-grid">
                    <div class="stat-box">
                        <div class="stat-number">{self.changes_summary['statistics']['total_current_files']}</div>
                        <div>Current Files</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{self.changes_summary['statistics']['new_files_count']}</div>
                        <div>New Files</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{self.changes_summary['statistics']['modified_files_count']}</div>
                        <div>Modified Files</div>
                    </div>
                    <div class="stat-box">
                        <div class="stat-number">{self.changes_summary['statistics']['deleted_files_count']}</div>
                        <div>Deleted Files</div>
                    </div>
                </div>
        """
        
        # Add sections for each change type
        if self.changes_summary['new_files']:
            html_content += f"""
                <h2 class="new">🆕 New Files ({len(self.changes_summary['new_files'])})</h2>
                <div class="file-list">
                    {''.join([f'<div class="file-item new">✅ {file}</div>' for file in self.changes_summary['new_files']])}
                </div>
            """
        
        if self.changes_summary['modified_files']:
            html_content += f"""
                <h2 class="modified">🔄 Modified Files ({len(self.changes_summary['modified_files'])})</h2>
                <div class="file-list">
                    {''.join([f'<div class="file-item modified">📝 {file}</div>' for file in self.changes_summary['modified_files']])}
                </div>
            """
        
        if self.changes_summary['deleted_files']:
            html_content += f"""
                <h2 class="deleted">🗑️ Deleted Files ({len(self.changes_summary['deleted_files'])})</h2>
                <div class="file-list">
                    {''.join([f'<div class="file-item deleted">❌ {file}</div>' for file in self.changes_summary['deleted_files']])}
                </div>
            """
        
        html_content += f"""
                <h2>📊 Individual File Analyses</h2>
                <ul>
                    <li>Individual financial pattern analyses available in visualizations folder</li>
                </ul>
                
                <div class="timestamp">
                    Report generated on: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                </div>
            </div>
        </body>
        </html>
        """
        
        # Save HTML report
        html_file = f"{self.report_folder}/daily_comparison_report_{self.current_date}.html"
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"📊 HTML report saved: {html_file}")

    def create_individual_file_analyses(self):
        """Create individual file analysis HTML pages"""
        if not self.changes_summary['modified_files']:
            print("📊 No modified files to analyze")
            return
            
        for filename in self.changes_summary['modified_files']:
            if filename not in self.changes_summary['content_changes']:
                continue
            
            change_data = self.changes_summary['content_changes'][filename]
            if 'metrics_comparison' not in change_data:
                continue
            
            # Generate individual file HTML
            html_content = self.generate_individual_file_html(filename, change_data)
            
            # Save individual file analysis
            safe_filename = re.sub(r'[<>:"/\\|?*]', '_', filename.replace('.txt', ''))
            html_file = f"{self.report_folder}/visualizations/{safe_filename}_analysis.html"
            with open(html_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            print(f"📊 Individual analysis saved: {html_file}")

    def run_full_analysis(self):
        """Run complete comparison and reporting analysis"""
        print("🚀 Starting Daily Comparison Analysis...")
        print("=" * 60)
        
        # Find data folders
        current_folder, previous_folder = self.find_data_folders()
        
        if not current_folder:
            print("❌ Current day folder not found!")
            return
        
        if not previous_folder:
            print("❌ Previous day folder not found!")
            print("📝 Note: This might be the first run. No comparison possible.")
            return
        
        print(f"📁 Current folder: {current_folder}")
        print(f"📁 Previous folder: {previous_folder}")
        
        # Compare files
        self.compare_files(current_folder, previous_folder)
        
        # Generate reports
        print("\n📝 Generating reports...")
        self.generate_html_report()
        
        # Create individual file analyses
        print("\n🔍 Creating individual file analyses...")
        self.create_individual_file_analyses()
        
        # Generate centralized dashboard
        print("\n🎯 Creating centralized dashboard...")
        dashboard_file = self.generate_centralized_dashboard()
        
        # Send Teams notification if webhook URL is configured
        if self.teams_webhook_url:
            print("\n📢 Sending Teams notification...")
            dashboard_url = f"file:///{os.path.abspath(dashboard_file).replace(os.sep, '/')}"
            self.send_teams_notification(self.teams_webhook_url, dashboard_url)
        else:
            print("\n💡 Teams webhook URL not configured - skipping notification")
        
        # Save summary as JSON (removed per user request)
        # json_file = f"{self.report_folder}/changes_summary_{self.current_date}.json"
        # with open(json_file, 'w', encoding='utf-8') as f:
        #     json.dump(self.changes_summary, f, indent=2, default=str)
        
        print("\n" + "=" * 60)
        print("✅ ANALYSIS COMPLETE!")
        print(f"📁 All reports saved in: {self.report_folder}")
        print(f"🎯 MAIN DASHBOARD: {self.report_folder}/financial_analysis_dashboard.html")
        print(f"📊 Statistics:")
        stats = self.changes_summary['statistics']
        print(f"   • Total files analyzed: {stats['total_current_files']}")
        print(f"   • New files: {stats['new_files_count']}")
        print(f"   • Modified files: {stats['modified_files_count']}")
        print(f"   • Deleted files: {stats['deleted_files_count']}")
        print(f"   • Unchanged files: {stats['unchanged_files_count']}")
        if self.changes_summary['modified_files']:
            print(f"🔍 Individual analyses available for:")
            for filename in self.changes_summary['modified_files'][:5]:  # Show first 5
                print(f"   • {filename}")
            if len(self.changes_summary['modified_files']) > 5:
                print(f"   • ... and {len(self.changes_summary['modified_files']) - 5} more")
        print("=" * 60)

def main():
    print("📊 DAILY FINANCIAL DATA COMPARISON REPORTER")
    print("=" * 60)
    print("🎯 Mission: Compare daily financial data extractions")
    print("📈 Features: Detailed financial pattern analysis and centralized dashboard")
    print("📁 Output: HTML reports and individual file analyses")
    print("📢 Teams Integration: Automatic notifications for pattern changes")
    print("=" * 60)
    
    # Get Teams webhook URL from environment variable or config file
    teams_webhook = os.environ.get('TEAMS_WEBHOOK_URL')
    
    # Try to load from config file if not in environment
    if not teams_webhook:
        try:
            config_file = os.path.join(os.path.dirname(__file__), 'teams_config.json')
            with open(config_file, 'r') as f:
                config = json.load(f)
                teams_webhook = config.get('teams_webhook_url')
        except FileNotFoundError:
            pass
    
    # Create reporter and run analysis
    print("📊 Daily Comparison Reporter initialized")
    reporter = DailyComparisonReporter(teams_webhook_url=teams_webhook)
    print(f"📅 Comparing: {reporter.previous_date} vs {reporter.current_date}")
    print(f"📁 Report folder: {reporter.report_folder}")
    if teams_webhook:
        print("📢 Teams notifications: ENABLED")
    else:
        print("📢 Teams notifications: DISABLED (set TEAMS_WEBHOOK_URL environment variable to enable)")
    
    reporter.run_full_analysis()

if __name__ == "__main__":
    main()

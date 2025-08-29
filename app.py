#!/usr/bin/env python3
"""
Enhanced Smart Financial Data Extractor (Crawl4AI version with PDF Processing)
- Recursively follows links from a given URL
- Skips generic pages (about, contact, etc.)
- Only creates files for pages containing financial data (rates, costs, tax percentages)
- Enhanced PDF and document processing capabilities
- Organizes content in a structured folder
- Single-threaded async implementation
"""
import asyncio
import re
import os
import time
import requests
from urllib.parse import urljoin, urlparse
from typing import Set, List, Dict
from datetime import datetime
from crawl4ai import AsyncWebCrawler
import PyPDF2
import io
from pathlib import Path
from collections import deque

# Generic pages to skip
SKIP_PATTERNS = [
    'about', 'contact', 'privacy', 'terms', 'sitemap', 'search', 'accessibility',
    'translate', 'home', 'index', 'faq', 'help', 'support', 'blog',
    'careers', 'jobs', 'staff', 'directory', 'media', 'press', 'calendar',
    'events', 'gallery', 'photo', 'video', 'social', 'facebook', 'twitter',
    'instagram', 'linkedin', 'youtube'
]

# Financial-related keywords to prioritize links
FINANCIAL_LINK_KEYWORDS = [
    'tax', 'fee', 'rate', 'cost', 'price', 'budget', 'financial', 'finance',
    'revenue', 'assessment', 'penalty', 'payment', 'billing', 'invoice',
    'permit', 'license', 'registration', 'business', 'property', 'sales',
    'income', 'audit', 'treasury', 'accounting', 'fiscal', 'economic'
]

# Financial keywords to detect valuable content
FINANCIAL_KEYWORDS = [
    r'\b\d+\.?\d*\s*%', r'\b\d+\.\d+\s*percent', r'\brate\s*of\s*\d+',
    r'\btax\s*rate\s*\d+', r'\binterest\s*rate\s*\d+', r'\b\d+\s*basis\s*points',
    r'\$\d+(?:,\d{3})*(?:\.\d{2})?', r'\$\d+\s*million', r'\$\d+\s*billion',
    r'\bcost\s*of\s*\$?\d+', r'\bfee\s*of\s*\$?\d+', r'\bcharge\s*\$?\d+',
    r'\bprice\s*\$?\d+', r'\bamount\s*\$?\d+', r'\bpayment\s*\$?\d+',
    r'\btax\s*\$?\d+', r'\bduty\s*\$?\d+', r'\bpenalty\s*\$?\d+', r'\bfine\s*\$?\d+',
    r'\btaxable\s*income', r'\btax\s*liability', r'\btax\s*assessment',
    r'\bfee\s*schedule', r'\brate\s*schedule', r'\bprice\s*list', r'\bcost\s*structure',
    r'\blicense\s*fee\s*\$?\d+', r'\bregistration\s*fee\s*\$?\d+', r'\bprocessing\s*fee\s*\$?\d+',
    r'\bdetermined\s*by', r'\btax\s*Assessment'
]

class EnhancedFinancialDataExtractor:
    def __init__(self, base_url: str, output_folder: str):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
        self.output_folder = output_folder
        self.docs_folder = os.path.join(output_folder, "documents")
        
        # Single-threaded data structures
        self.visited_urls = set()
        self.financial_pages = []
        self.failed_pages = []
        self.skipped_pages = []
        
        # Create directories
        os.makedirs(self.output_folder, exist_ok=True)
        os.makedirs(self.docs_folder, exist_ok=True)
        
        print(f"🔧 Enhanced extractor initialized for domain: {self.domain}")
        print(f"📁 Output folder: {self.output_folder}")
        print(f"📋 Documents folder: {self.docs_folder}")

    def is_generic_page(self, url: str) -> bool:
        """Check if URL is a generic page to skip"""
        url_lower = url.lower()
        path = urlparse(url).path.lower()
        
        for pattern in SKIP_PATTERNS:
            if pattern in url_lower or f'/{pattern}' in path:
                return True
        return False

    def is_pdf_url(self, url: str) -> bool:
        """Check if URL points to a PDF document"""
        return url.lower().endswith('.pdf') or 'pdf' in url.lower()
    
    def is_document_url(self, url: str) -> bool:
        """Check if URL points to any document type"""
        doc_extensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
        url_lower = url.lower()
        return any(ext in url_lower for ext in doc_extensions)

    def contains_financial_data(self, text: str) -> tuple[bool, List[str]]:
        """Check if text contains financial information"""
        if not text:
            return False, []
        
        found_patterns = []
        for pattern in FINANCIAL_KEYWORDS:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                found_patterns.extend(matches[:3])  # Limit to first 3 matches per pattern
                
        return len(found_patterns) > 0, found_patterns

    def get_safe_filename(self, url: str) -> str:
        """Convert URL to safe filename"""
        parsed = urlparse(url)
        path = parsed.path.strip('/').replace('/', '_')
        
        if not path or path == '_':
            path = parsed.netloc.replace('.', '_')
        
        # Clean the filename
        safe_chars = re.sub(r'[<>:"/\\|?*%]', '_', path)
        safe_chars = re.sub(r'_+', '_', safe_chars)
        safe_chars = safe_chars.strip('_')
        
        if not safe_chars:
            safe_chars = f"page_{hash(url) % 10000}"
            
        return f"{safe_chars}.txt"

    async def download_and_process_pdf(self, url: str) -> Dict:
        """Download and extract text from PDF documents with improved error handling"""
        print(f"📄 Processing PDF: {url}")
        
        try:
            # Enhanced request with better headers and longer timeout
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'application/pdf,application/octet-stream,*/*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
            }
            
            # Use session for better connection handling
            session = requests.Session()
            session.headers.update(headers)
            
            # Multiple retry attempts with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    print(f"   🔄 Attempt {attempt + 1}/{max_retries}")
                    response = session.get(url, timeout=60, stream=True)
                    response.raise_for_status()
                    
                    # Check if it's actually a PDF
                    content_type = response.headers.get('content-type', '').lower()
                    if 'pdf' not in content_type and not url.lower().endswith('.pdf'):
                        return {"url": url, "status": "FAILED", "error": "Not a valid PDF document", "type": "PDF"}
                    
                    # Download with progress tracking
                    content = b""
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded = 0
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            content += chunk
                            downloaded += len(chunk)
                            if total_size > 0 and downloaded % (1024 * 100) == 0:  # Every 100KB
                                progress = (downloaded / total_size) * 100
                                print(f"   📥 Downloaded {progress:.1f}% ({downloaded}/{total_size} bytes)")
                    
                    print(f"   ✅ PDF downloaded: {len(content)} bytes")
                    break
                    
                except requests.exceptions.Timeout:
                    print(f"   ⏰ Timeout on attempt {attempt + 1}")
                    if attempt == max_retries - 1:
                        return {"url": url, "status": "FAILED", "error": "Timeout after multiple attempts", "type": "PDF"}
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
                except requests.exceptions.ConnectionError as e:
                    print(f"   🔌 Connection error on attempt {attempt + 1}: {str(e)[:50]}")
                    if attempt == max_retries - 1:
                        return {"url": url, "status": "FAILED", "error": f"Connection failed: {str(e)[:100]}", "type": "PDF"}
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                    continue
                    
            # Extract text from PDF
            pdf_text = ""
            try:
                pdf_file = io.BytesIO(content)
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                
                print(f"   📖 PDF has {len(pdf_reader.pages)} pages")
                
                for page_num in range(len(pdf_reader.pages)):
                    try:
                        page = pdf_reader.pages[page_num]
                        page_text = page.extract_text()
                        if page_text:
                            pdf_text += f"\n--- PAGE {page_num + 1} ---\n{page_text}\n"
                    except Exception as page_error:
                        print(f"   ⚠️  Error reading page {page_num + 1}: {str(page_error)[:50]}")
                        continue
                
                if pdf_text.strip():
                    print(f"   ✅ Successfully extracted {len(pdf_text)} characters from PDF")
                    return {
                        "url": url,
                        "title": f"PDF Document - {Path(urlparse(url).path).name}",
                        "content": pdf_text,
                        "links": [],
                        "status": "SUCCESS",
                        "type": "PDF"
                    }
                else:
                    # Even if no text, save metadata about the PDF
                    metadata_content = f"""PDF Document Information:
URL: {url}
File Size: {len(content)} bytes
Pages: {len(pdf_reader.pages) if 'pdf_reader' in locals() else 'Unknown'}
Content Type: {content_type}
Download Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Note: This PDF exists but no text could be extracted. It may contain images, scanned text, or be password protected.
This could still be a valuable financial document that should be reviewed manually.
"""
                    return {
                        "url": url,
                        "title": f"PDF Document (No Text) - {Path(urlparse(url).path).name}",
                        "content": metadata_content,
                        "links": [],
                        "status": "SUCCESS",
                        "type": "PDF"
                    }
                    
            except Exception as pdf_error:
                # Save what we can even if PDF processing fails
                error_content = f"""PDF Processing Error:
URL: {url}
File Size: {len(content)} bytes
Error: {str(pdf_error)}
Download Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Note: PDF was downloaded but could not be processed. This might be:
- A corrupted PDF file
- A password-protected PDF
- A PDF with complex formatting
- A scanned document without OCR text

Manual review may be required for this financial document.
"""
                return {
                    "url": url,
                    "title": f"PDF Document (Processing Error) - {Path(urlparse(url).path).name}",
                    "content": error_content,
                    "links": [],
                    "status": "SUCCESS",  # Still consider it success since we tried
                    "type": "PDF"
                }
                
        except Exception as e:
            return {"url": url, "status": "FAILED", "error": str(e)[:200], "type": "PDF"}

    async def download_and_process_document(self, url: str) -> Dict:
        """Download and process various document types"""
        print(f"📋 Processing Document: {url}")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # For now, just get basic info about other document types
            # You could add more specific processing for DOC, XLS, etc.
            content_type = response.headers.get('content-type', '').lower()
            file_size = len(response.content)
            
            # Basic content extraction attempt
            document_info = f"""
Document URL: {url}
Content Type: {content_type}
File Size: {file_size} bytes
Downloaded: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

Note: This is a {content_type} document. Enhanced processing for this file type could be implemented.
Raw content preview (first 500 chars):
{response.content[:500].decode('utf-8', errors='ignore')}
"""
            
            return {
                "url": url,
                "title": f"Document - {Path(urlparse(url).path).name}",
                "content": document_info,
                "links": [],
                "status": "SUCCESS",
                "type": "DOCUMENT"
            }
            
        except Exception as e:
            return {"url": url, "status": "FAILED", "error": str(e)[:100], "type": "DOCUMENT"}

    async def scrape_page(self, crawler: AsyncWebCrawler, url: str) -> Dict:
        """Scrape a single page with enhanced document processing"""
        print(f"🔍 Scraping: {url}")
        
        # Check if it's a document URL
        if self.is_document_url(url):
            if url.lower().endswith('.pdf'):
                return await self.download_and_process_pdf(url)
            else:
                return await self.download_and_process_document(url)
        
        # Regular web page scraping with retry logic
        max_retries = 2
        for attempt in range(max_retries):
            try:
                print(f"   🔄 Attempt {attempt + 1}/{max_retries}")
                result = await crawler.arun(
                    url=url, 
                    extract_links=True,
                    html2text=True,
                    css_selector="a[href]",  # Ensure we get all links
                    page_timeout=30000,  # 30 second timeout
                    wait_for="networkidle0",  # Wait for network to be idle
                    bypass_cache=True,
                    simulate_user=True
                )
                break  # Success, exit retry loop
            except Exception as retry_error:
                print(f"   ⚠️  Retry {attempt + 1} failed: {str(retry_error)[:60]}")
                if attempt == max_retries - 1:
                    return {"url": url, "status": "FAILED", "error": f"Max retries exceeded: {str(retry_error)[:100]}", "type": "WEBPAGE"}
                await asyncio.sleep(3)  # Wait before retry
        
        try:
            if result and result.markdown:
                # Extract links from both the result.links and by parsing HTML
                links = []
                
                # Try to get links from result.links first
                if hasattr(result, 'links') and result.links:
                    for link_data in result.links:
                        if isinstance(link_data, dict):
                            href = link_data.get('href', '') or link_data.get('url', '')
                            text = link_data.get('text', '') or link_data.get('title', '')
                            if href:
                                links.append({'url': href, 'text': text})
                        else:
                            links.append({'url': str(link_data), 'text': ''})
                
                # If we don't have many links, try to extract from HTML
                if len(links) < 5 and hasattr(result, 'html') and result.html:
                    import re
                    # Extract href attributes from HTML
                    href_pattern = r'<a[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>'
                    html_links = re.findall(href_pattern, result.html, re.IGNORECASE)
                    for href, text in html_links:
                        if href not in [l['url'] for l in links]:
                            links.append({'url': href, 'text': text.strip()})
                
                return {
                    "url": url,
                    "title": result.metadata.get("title", "No Title") if result.metadata else "No Title",
                    "content": result.markdown,
                    "links": links,
                    "status": "SUCCESS",
                    "type": "WEBPAGE"
                }
            else:
                return {"url": url, "status": "FAILED", "error": "No content returned", "type": "WEBPAGE"}
        except Exception as e:
            return {"url": url, "status": "FAILED", "error": str(e)[:100], "type": "WEBPAGE"}

    def save_content(self, page_data: Dict, save_dir: str):
        """Save page content to appropriate folder"""
        filename = self.get_safe_filename(page_data["url"])
        
        # Use documents folder for PDFs and other documents
        if page_data.get("type") in ["PDF", "DOCUMENT"]:
            filepath = os.path.join(self.docs_folder, filename)
        else:
            filepath = os.path.join(save_dir, filename)
        
        # Prepare content with metadata
        content = f"""URL: {page_data['url']}
TITLE: {page_data['title']}
TYPE: {page_data.get('type', 'WEBPAGE')}
SCRAPED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
{'-' * 60}

{page_data['content']}
"""
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"💾 Saved content: {os.path.basename(filepath)}")
            return filepath
            
        except Exception as e:
            print(f"❌ Failed to save file {filename}: {e}")
            return None

    def save_financial_content(self, page_data: Dict, financial_patterns: List[str]):
        """Save page content to file if it contains financial data"""
        filename = self.get_safe_filename(page_data["url"])
        
        # Use documents folder for PDFs and other documents
        if page_data.get("type") in ["PDF", "DOCUMENT"]:
            filepath = os.path.join(self.docs_folder, filename)
        else:
            filepath = os.path.join(self.output_folder, filename)
        
        # Prepare content with metadata
        content = f"""URL: {page_data['url']}
TITLE: {page_data['title']}
TYPE: {page_data.get('type', 'WEBPAGE')}
SCRAPED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
FINANCIAL PATTERNS FOUND: {len(financial_patterns)}
{'-' * 60}
DETECTED PATTERNS:
{', '.join(financial_patterns[:10])}

{'-' * 60}
CONTENT:

{page_data['content']}
"""
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"💾 Saved financial content: {os.path.basename(filepath)}")
            print(f"   📊 Found {len(financial_patterns)} financial indicators")
            
            # Store info for summary
            if hasattr(self, 'saved_files'):
                self.saved_files.append({
                    "url": page_data["url"], 
                    "title": page_data["title"],
                    "filename": filename,
                    "patterns": len(financial_patterns)
                })
            
            return filepath
            
        except Exception as e:
            print(f"❌ Failed to save file {filename}: {e}")
            return None

    def extract_links(self, page_data: Dict) -> List[str]:
        """Extract valid links from page data, prioritizing financial links and documents"""
        financial_links = []
        document_links = []
        other_links = []
        
        for link_data in page_data.get("links", []):
            # Handle both string and dict formats
            if isinstance(link_data, dict):
                link = link_data.get('url', '') or link_data.get('href', '')
                link_text = link_data.get('text', '')
            else:
                link = str(link_data)
                link_text = ""
            
            if not link:
                continue
                
            # Convert to absolute URL
            if link.startswith('/'):
                full_url = f"https://{self.domain}{link}"
            elif link.startswith('http'):
                # Only keep links from the same domain
                if self.domain not in link:
                    continue
                full_url = link
            elif link.startswith('#') or link.startswith('mailto:') or link.startswith('tel:'):
                continue  # Skip anchor links and non-web links
            else:
                # Relative links without leading slash
                full_url = f"https://{self.domain}/{link.lstrip('/')}"
            
            # Clean URL (remove anchors and query params for comparison)
            clean_url = full_url.split('#')[0].split('?')[0]
            
            # Skip if already visited or is generic page
            if clean_url in self.visited_urls or self.is_generic_page(clean_url):
                continue
                
            # Categorize links by type and financial relevance
            if self.is_document_url(clean_url):
                document_links.append(clean_url)
            elif any(keyword in clean_url.lower() or keyword in link_text.lower() 
                    for keyword in FINANCIAL_LINK_KEYWORDS):
                financial_links.append(clean_url)
            else:
                other_links.append(clean_url)
        
        # Prioritize document links, then financial links, then others (limited)
        max_other_links = 5  # Limit other links to prevent explosion
        selected_links = document_links + financial_links + other_links[:max_other_links]
        
        # Remove duplicates while preserving order
        unique_links = []
        for link in selected_links:
            if link not in unique_links:
                unique_links.append(link)
        
        if document_links:
            print(f"   📋 Found {len(document_links)} document links, {len(financial_links)} financial links, {len(other_links[:max_other_links])} other links")
        elif financial_links:
            print(f"   🎯 Found {len(financial_links)} financial links, {len(other_links[:max_other_links])} other links")
        else:
            print(f"   📄 Found {len(unique_links)} general links")
            
        return unique_links

    async def recursive_extract(self, start_url: str, max_depth: int = 3, max_pages: int = 50):
        """Recursively extract financial data from website with enhanced document processing"""
        print(f"🚀 ENHANCED SMART FINANCIAL DATA EXTRACTION STARTED")
        print(f"📍 Starting URL: {start_url}")
        print(f"🎯 Target: Pages with financial data (rates, costs, taxes)")
        print(f"📋 Enhanced: PDF and document processing enabled")
        print(f"⚙️  Max Depth: {max_depth} | Max Pages: {max_pages}")
        print("=" * 70)
        
        # Use collections.deque for efficient queue operations
        urls_to_visit = deque([(start_url, 0)])
        pages_processed = 0

        async with AsyncWebCrawler() as crawler:
            while urls_to_visit and pages_processed < max_pages:
                current_url, depth = urls_to_visit.popleft()  # Process from left (FIFO)
                
                if current_url in self.visited_urls or depth > max_depth:
                    continue
                    
                if self.is_generic_page(current_url):
                    self.skipped_pages.append(current_url)
                    print(f"⏭️  Skipping generic page: {current_url}")
                    continue

                self.visited_urls.add(current_url)
                pages_processed += 1
                print(f"\n📄 Page {pages_processed}/{max_pages} (Depth: {depth})")
                print(f"🌐 Queue has {len(urls_to_visit)} remaining URLs to process")

                page_data = await self.scrape_page(crawler, current_url)
                
                if page_data.get("status") == "SUCCESS":
                    has_financial, patterns = self.contains_financial_data(page_data["content"])
                    
                    if has_financial:
                        filepath = self.save_financial_content(page_data, patterns)
                        if filepath:
                            self.financial_pages.append({
                                "url": current_url,
                                "title": page_data["title"],
                                "filepath": filepath,
                                "patterns": patterns[:10],
                                "depth": depth,
                                "type": page_data.get("type", "WEBPAGE")
                            })
                    else:
                        print(f"⚪ No financial data found, skipping file creation")

                    # Extract links for next level if not at max depth
                    if depth < max_depth:
                        new_links = self.extract_links(page_data)
                        
                        # Add new links to the queue with incremented depth
                        new_urls_added = 0
                        for link in new_links:
                            if link not in self.visited_urls and not any(url == link for url, d in urls_to_visit):
                                urls_to_visit.append((link, depth + 1))
                                new_urls_added += 1
                        
                        if new_urls_added > 0:
                            print(f"🔗 Added {new_urls_added} new URLs to queue (Queue size: {len(urls_to_visit)})")
                        else:
                            print(f"🔗 No new URLs to add (all already visited or queued)")
                else:
                    self.failed_pages.append(current_url)
                    print(f"❌ Failed to scrape: {page_data.get('error', 'Unknown error')}")

                # Rate limiting - increased delay for better server cooperation
                await asyncio.sleep(3)  # Respectful delay between requests

        self.print_summary()

    def print_summary(self):
        """Print comprehensive summary of extraction results"""
        print("\n" + "=" * 80)
        print("🎯 ENHANCED FINANCIAL DATA EXTRACTION COMPLETED!")
        print("=" * 80)
        print(f"📊 STATISTICS:")
        print(f"   • Total pages processed: {len(self.visited_urls)}")
        print(f"   • Financial pages found: {len(self.financial_pages)}")
        print(f"   • PDF documents processed: {len([p for p in self.financial_pages if p.get('type') == 'PDF'])}")
        print(f"   • Generic pages skipped: {len(self.skipped_pages)}")
        print(f"   • Failed pages: {len(self.failed_pages)}")
        
        if self.financial_pages:
            print(f"\n💰 FINANCIAL CONTENT SAVED ({len(self.financial_pages)} files):")
            print("-" * 50)
            
            # Separate by type
            webpages = [p for p in self.financial_pages if p.get('type') != 'PDF']
            pdfs = [p for p in self.financial_pages if p.get('type') == 'PDF']
            
            # Show webpages
            for i, page in enumerate(webpages, 1):
                print(f"{i:2d}. {page['title'][:50]}")
                print(f"    URL: {page['url']}")
                print(f"    File: {os.path.basename(page['filepath'])}")
                print(f"    Patterns: {', '.join(page['patterns'][:5])}")
                print()
            
            # Show PDFs separately
            if pdfs:
                print(f"📋 PDF DOCUMENTS PROCESSED ({len(pdfs)}):")
                print("-" * 30)
                for i, page in enumerate(pdfs, 1):
                    print(f"{i:2d}. {page['title'][:50]}")
                    print(f"    URL: {page['url']}")
                    print(f"    File: documents/{os.path.basename(page['filepath'])}")
                    print(f"    Patterns: {', '.join(page['patterns'][:5])}")
                    print()
        
        if self.skipped_pages:
            print(f"⏭️  GENERIC PAGES SKIPPED ({len(self.skipped_pages)}):")
            for url in self.skipped_pages[:10]:  # Show first 10
                print(f"   • {url}")
            if len(self.skipped_pages) > 10:
                print(f"   • ... and {len(self.skipped_pages) - 10} more")
        
        if self.failed_pages:
            print(f"\n❌ FAILED PAGES ({len(self.failed_pages)}):")
            for url in self.failed_pages:
                print(f"   • {url}")
        
        print(f"\n📁 All financial content saved in: {self.output_folder}/")
        print(f"📋 PDF documents saved in: {self.docs_folder}/")

def main():
    # Configuration - Start from homepage to get more links
    start_url = "https://dor.sd.gov/newsroom/"
    
    # Create output folder with current date
    current_date = datetime.now().strftime("%Y%m%d")
    output_folder = f"clean_enhanced_la_finance_data_{current_date}"
    
    print("🏛️  ENHANCED SMART FINANCIAL DATA EXTRACTOR (Crawl4AI)")
    print("=" * 60)
    print("🎯 Mission: Extract ONLY pages with financial data")
    print("⚡ Strategy: Skip generic pages, follow financial links")
    print("💾 Output: Create files only for financial content")
    print("🤖 Engine: Crawl4AI AsyncWebCrawler with PDF Processing")
    print("📋 Features: Enhanced PDF and document processing")
    print("🔧 Architecture: Single-threaded async implementation")
    print("=" * 60)
    
    # Create extractor and start extraction
    extractor = EnhancedFinancialDataExtractor(start_url, output_folder)
    asyncio.run(extractor.recursive_extract(
        start_url=start_url,
        max_depth=3,
        max_pages=100  # Process many pages to follow all discovered links
    ))

if __name__ == "__main__":
    main()

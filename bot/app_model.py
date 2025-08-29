import asyncio
import sys
import warnings
import nest_asyncio
from typing import Dict, List, Optional
from datetime import datetime
import os
import re

# Import the enhanced extractor
from app import EnhancedFinancialDataExtractor

# Modern LangChain imports (non-deprecated)
from langchain_community.llms import Ollama
from langchain.agents import AgentExecutor, create_react_agent
from langchain.tools import Tool, StructuredTool
from langchain.memory import ConversationBufferMemory
from langchain.prompts import PromptTemplate
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.schema import SystemMessage, HumanMessage
from pydantic import BaseModel, Field

# Fix for Windows + async environment
if sys.platform.startswith('win'):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Allow nested async loops
nest_asyncio.apply()

# Initialize the LLM
llm = Ollama(
    model="qwen3",  # or "mistral:7b" 
    temperature=0.3,
    num_predict=2048
)

# Global extractor instance
global_extractor = None

def get_or_create_extractor(base_url: str = None) -> EnhancedFinancialDataExtractor:
    """Get existing extractor or create new one"""
    global global_extractor
    
    if global_extractor is None or (base_url and global_extractor.base_url != base_url):
        # Create output folder with current date
        current_date = datetime.now().strftime("%Y%m%d")
        output_folder = f"agent_extracted_data_{current_date}"
        
        if base_url is None:
            base_url = "https://example.com"  # Default URL
            
        global_extractor = EnhancedFinancialDataExtractor(base_url, output_folder)
    
    return global_extractor

def clean_url(url: str) -> str:
    """Clean URL from any markdown formatting or special characters"""
    import re
    # Remove markdown code blocks and backticks
    clean = re.sub(r'```.*?$', '', url, flags=re.MULTILINE)
    clean = re.sub(r'[`\n\r]', '', clean)
    clean = clean.strip()
    # Ensure proper URL format
    if not clean.startswith(('http://', 'https://')):
        clean = 'https://' + clean
    return clean

def parse_crawl_input(input_str: str) -> tuple:
    """Parse the input string for crawl_financial_data tool, handling special characters"""
    import re
    
    # Clean the input string - remove markdown formatting and special characters
    clean_input = re.sub(r'```.*?$', '', input_str, flags=re.MULTILINE)  # Remove markdown code blocks
    clean_input = re.sub(r'[`\n\r]', '', clean_input)  # Remove backticks and newlines
    clean_input = clean_input.strip()
    
    # Split by comma and clean each part
    parts = [part.strip() for part in clean_input.split(',')]
    
    # Parse URL (required) - use clean_url function
    url = clean_url(parts[0]) if parts else "https://example.com"
    
    # Parse max_depth (optional, default 2)
    max_depth = 2
    if len(parts) > 1:
        try:
            # Extract just the digits from the string
            depth_str = re.findall(r'\d+', parts[1])
            max_depth = int(depth_str[0]) if depth_str else 2
        except (ValueError, IndexError):
            max_depth = 2
    
    # Parse max_pages (optional, default 20)
    max_pages = 20
    if len(parts) > 2:
        try:
            # Extract just the digits from the string
            pages_str = re.findall(r'\d+', parts[2])
            max_pages = int(pages_str[0]) if pages_str else 20
        except (ValueError, IndexError):
            max_pages = 20
    
    return url, max_depth, max_pages

# Tool Functions using the Enhanced Extractor
async def crawl_and_extract_financial_data(url: str, max_depth: int = 2, max_pages: int = 20) -> str:
    """
    Crawl a website and extract financial data (taxes, fees, rates, costs).
    Returns a summary of financial information found.
    """
    try:
        # Clean the URL
        url = clean_url(url)
        
        extractor = get_or_create_extractor(url)
        
        # Run the extraction
        await extractor.recursive_extract(
            start_url=url,
            max_depth=max_depth,
            max_pages=max_pages
        )
        
        # Prepare summary
        summary = f"""
Financial Data Extraction Results:
==================================
📍 URL: {url}
📊 Total pages processed: {len(extractor.visited_urls)}
💰 Financial pages found: {len(extractor.financial_pages)}
📋 PDF documents processed: {len([p for p in extractor.financial_pages if p.get('type') == 'PDF'])}

Financial Content Found:
------------------------
"""
        
        for i, page in enumerate(extractor.financial_pages[:10], 1):
            summary += f"\n{i}. {page['title'][:50]}"
            summary += f"\n   Type: {page.get('type', 'WEBPAGE')}"
            summary += f"\n   URL: {page['url']}"
            summary += f"\n   Patterns: {', '.join(page['patterns'][:5])}\n"
        
        if len(extractor.financial_pages) > 10:
            summary += f"\n... and {len(extractor.financial_pages) - 10} more financial pages"
        
        summary += f"\n\n📁 Data saved in: {extractor.output_folder}/"
        
        return summary
        
    except Exception as e:
        return f"Error extracting financial data: {str(e)}"

async def process_pdf_document(pdf_url: str) -> str:
    """
    Process a PDF document and extract text content using multiple methods including OCR.
    Returns the extracted text or error message.
    """
    try:
        # Clean the URL
        pdf_url = clean_url(pdf_url)
        
        extractor = get_or_create_extractor()
        
        # Process the PDF
        result = await extractor.download_and_process_pdf(pdf_url)
        
        if result.get("status") == "SUCCESS":
            content = result.get("content", "")
            title = result.get("title", "Unknown")
            
            # Check for financial patterns
            has_financial, patterns = extractor.contains_financial_data(content)
            
            summary = f"""
PDF Processing Results:
====================
📄 Title: {title}
🔗 URL: {pdf_url}
📊 Financial patterns found: {len(patterns) if has_financial else 0}

Extracted Content Preview (first 2000 chars):
---------------------------------------------
{content[:2000]}...

"""
            if has_financial:
                summary += f"\nFinancial Patterns Detected:\n{', '.join(patterns[:10])}"
            
            return summary
        else:
            return f"Failed to process PDF: {result.get('error', 'Unknown error')}"
            
    except Exception as e:
        return f"Error processing PDF: {str(e)}"

async def analyze_single_webpage(url: str) -> str:
    """
    Analyze a single webpage for financial information without recursive crawling.
    Returns financial data found on the page.
    """
    try:
        # Clean the URL
        url = clean_url(url)
        
        from crawl4ai import AsyncWebCrawler
        
        extractor = get_or_create_extractor(url)
        
        async with AsyncWebCrawler() as crawler:
            page_data = await extractor.scrape_page(crawler, url)
            
            if page_data.get("status") == "SUCCESS":
                content = page_data.get("content", "")
                has_financial, patterns = extractor.contains_financial_data(content)
                
                summary = f"""
Single Page Analysis:
====================
📍 URL: {url}
📄 Title: {page_data.get('title', 'No Title')}
🔗 Links found: {len(page_data.get('links', []))}
📊 Financial data: {'Yes' if has_financial else 'No'}

"""
                if has_financial:
                    summary += f"Financial Patterns Found:\n"
                    summary += f"{', '.join(patterns[:20])}\n\n"
                    
                    # Save if financial content found
                    filepath = extractor.save_financial_content(page_data, patterns)
                    if filepath:
                        summary += f"💾 Content saved to: {filepath}\n"
                
                summary += f"\nContent Preview (first 1000 chars):\n"
                summary += f"{'-' * 40}\n"
                summary += f"{content[:1000]}..."
                
                return summary
            else:
                return f"Failed to analyze page: {page_data.get('error', 'Unknown error')}"
                
    except Exception as e:
        return f"Error analyzing webpage: {str(e)}"

async def extract_links_from_page(url: str) -> str:
    """
    Extract all links from a webpage, categorized by type (financial, documents, other).
    """
    try:
        # Clean the URL
        url = clean_url(url)
        
        from crawl4ai import AsyncWebCrawler
        
        extractor = get_or_create_extractor(url)
        
        async with AsyncWebCrawler() as crawler:
            page_data = await extractor.scrape_page(crawler, url)
            
            if page_data.get("status") == "SUCCESS":
                links = extractor.extract_links(page_data)
                
                # Categorize links
                pdf_links = [l for l in links if l.lower().endswith('.pdf')]
                doc_links = [l for l in links if extractor.is_document_url(l) and not l.lower().endswith('.pdf')]
                financial_links = [l for l in links if any(kw in l.lower() for kw in ['tax', 'fee', 'rate', 'cost', 'budget'])]
                
                summary = f"""
Links Extracted from: {url}
============================
📋 Total links found: {len(links)}
📄 PDF documents: {len(pdf_links)}
📁 Other documents: {len(doc_links)}
💰 Financial links: {len(financial_links)}

PDF Documents:
--------------
"""
                for i, link in enumerate(pdf_links[:5], 1):
                    summary += f"{i}. {link}\n"
                
                if financial_links:
                    summary += f"\nFinancial Links:\n"
                    summary += f"----------------\n"
                    for i, link in enumerate(financial_links[:10], 1):
                        summary += f"{i}. {link}\n"
                
                summary += f"\nAll Links:\n"
                summary += f"----------\n"
                for i, link in enumerate(links[:20], 1):
                    summary += f"{i}. {link}\n"
                    
                if len(links) > 20:
                    summary += f"\n... and {len(links) - 20} more links"
                
                return summary
            else:
                return f"Failed to extract links: {page_data.get('error', 'Unknown error')}"
                
    except Exception as e:
        return f"Error extracting links: {str(e)}"

# Create Tools for the Agent
tools = [
    Tool(
        name="crawl_financial_data",
        func=lambda input_str: asyncio.run(
            crawl_and_extract_financial_data(
                *parse_crawl_input(input_str)
            )
        ),
        description="Crawl a website recursively to extract financial data (taxes, fees, rates). Input: 'url' or 'url,max_depth,max_pages'. Example: 'https://example.com,3,50'"
    ),
    Tool(
        name="process_pdf",
        func=lambda pdf_url: asyncio.run(process_pdf_document(clean_url(pdf_url))),
        description="Process a PDF document and extract text using OCR if needed. Input: PDF URL. Returns extracted text content."
    ),
    Tool(
        name="analyze_webpage",
        func=lambda url: asyncio.run(analyze_single_webpage(clean_url(url))),
        description="Analyze a single webpage for financial information without recursive crawling. Input: webpage URL."
    ),
    Tool(
        name="extract_links",
        func=lambda url: asyncio.run(extract_links_from_page(clean_url(url))),
        description="Extract all links from a webpage, categorized by type (PDFs, documents, financial). Input: webpage URL."
    )
]

def parse_instructions_file(filepath: str) -> Dict:
    """Parse the instructions file and extract structured information"""
    try:
        with open(filepath, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Initialize result dictionary
        instructions = {
            'urls': [],
            'target_data': [],
            'specific_instructions': [],
            'max_depth': 3,
            'max_pages': 50,
            'full_text': content
        }
        
        # Extract URLs (look for lines starting with http/https or containing URL:)
        url_patterns = [
            r'(?:URL|url|Website|website|Site|site):\s*(https?://[^\s]+)',
            r'^(https?://[^\s]+)',
            r'^\s*[-•*]\s*(https?://[^\s]+)'
        ]
        
        for pattern in url_patterns:
            urls = re.findall(pattern, content, re.MULTILINE)
            instructions['urls'].extend(urls)
        
        # Remove duplicates
        instructions['urls'] = list(set(instructions['urls']))
        
        # Extract target data types
        if re.search(r'(?:tax|Tax|TAX)', content):
            instructions['target_data'].append('tax rates and information')
        if re.search(r'(?:fee|Fee|FEE)', content):
            instructions['target_data'].append('fees and charges')
        if re.search(r'(?:rate|Rate|RATE)', content):
            instructions['target_data'].append('rates and percentages')
        if re.search(r'(?:cost|Cost|COST|price|Price)', content):
            instructions['target_data'].append('costs and pricing')
        if re.search(r'(?:budget|Budget|BUDGET)', content):
            instructions['target_data'].append('budget information')
        if re.search(r'(?:permit|Permit|license|License)', content):
            instructions['target_data'].append('permits and licenses')
        
        # Extract max depth/pages if specified
        depth_match = re.search(r'(?:depth|Depth|DEPTH)[:\s]*(\d+)', content)
        if depth_match:
            instructions['max_depth'] = int(depth_match.group(1))
        
        pages_match = re.search(r'(?:pages|Pages|PAGES)[:\s]*(\d+)', content)
        if pages_match:
            instructions['max_pages'] = int(pages_match.group(1))
        
        # Extract specific instructions (lines after keywords like "Instructions:", "Steps:", etc.)
        instruction_sections = re.findall(
            r'(?:Instructions?|Steps?|Tasks?|Requirements?|Goals?|Objectives?):\s*\n((?:.*\n)*?)(?:\n\n|\Z)',
            content,
            re.IGNORECASE | re.MULTILINE
        )
        
        for section in instruction_sections:
            lines = section.strip().split('\n')
            instructions['specific_instructions'].extend([line.strip() for line in lines if line.strip()])
        
        return instructions
        
    except FileNotFoundError:
        print(f"❌ Error: File '{filepath}' not found")
        return None
    except Exception as e:
        print(f"❌ Error parsing instructions file: {str(e)}")
        return None

def create_autonomous_agent():
    """Create an autonomous agent that works based on instructions from a file"""
    
    # Create the React Agent Prompt Template for autonomous operation
    # Simplified prompt with single input variable
    autonomous_prompt = PromptTemplate.from_template("""You are an autonomous Financial Data Extraction Agent that works independently based on provided instructions.

Your mission is to thoroughly explore websites and extract all relevant financial information according to the user's requirements.

Your capabilities:
🌐 Web Crawling: Recursively crawl websites to find financial information
📊 Financial Analysis: Identify and extract taxes, fees, rates, costs, and other financial data
📄 PDF Processing: Extract text from PDF documents using OCR when needed
🔗 Link Analysis: Categorize and prioritize financial and document links

Available tools:
{tools}

Tool Names: {tool_names}

To use a tool, you must use the following format:
```
Thought: I need to [explain what you need to do]
Action: [tool_name]
Action Input: [input for the tool]
```

After receiving the tool's output:
```
Observation: [tool output will appear here]
```

Continue this process until you have thoroughly explored all URLs and extracted all relevant financial information, then provide your final answer:
```
Thought: I have completed the extraction task
Final Answer: [comprehensive summary of all financial data found]
```

Task: {input}
{agent_scratchpad}

Begin your systematic exploration now!""")
    
    # Create memory
    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True
    )
    
    # Create the agent using create_react_agent
    agent = create_react_agent(
        llm=llm,
        tools=tools,
        prompt=autonomous_prompt
    )
    
    # Create the agent executor
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        memory=memory,
        verbose=True,
        max_iterations=15,  # Increased for thorough exploration
        handle_parsing_errors=True,
        early_stopping_method="generate"
    )
    
    return agent_executor

def run_autonomous_extraction(instructions_file: str):
    """Run the autonomous agent based on instructions from a file"""
    
    print("=" * 80)
    print("🤖 AUTONOMOUS FINANCIAL DATA EXTRACTION AGENT")
    print("=" * 80)
    
    # Parse instructions file
    print(f"📄 Reading instructions from: {instructions_file}")
    instructions = parse_instructions_file(instructions_file)
    
    if not instructions:
        print("❌ Failed to parse instructions file")
        return
    
    # Display parsed instructions
    print("\n📋 Parsed Instructions:")
    print("-" * 40)
    print(f"URLs to process: {len(instructions['urls'])}")
    for url in instructions['urls']:
        print(f"  • {url}")
    print(f"\nTarget data types: {', '.join(instructions['target_data']) if instructions['target_data'] else 'All financial data'}")
    print(f"Max depth: {instructions['max_depth']}")
    print(f"Max pages: {instructions['max_pages']}")
    
    if instructions['specific_instructions']:
        print("\nSpecific instructions:")
        for inst in instructions['specific_instructions'][:5]:
            print(f"  • {inst}")
    
    print("\n" + "=" * 80)
    print("🚀 Starting autonomous extraction...")
    print("=" * 80)
    
    # Create the autonomous agent
    agent_executor = create_autonomous_agent()
    
    # Prepare a single consolidated input string
    consolidated_input = f"""
USER INSTRUCTIONS:
==================
{instructions['full_text']}

TARGET URLS TO PROCESS:
=======================
{chr(10).join(instructions['urls'])}

TARGET DATA TYPES:
==================
{', '.join(instructions['target_data']) if instructions['target_data'] else 'All financial data'}

SPECIFIC REQUIREMENTS:
====================
{chr(10).join(instructions['specific_instructions']) if instructions['specific_instructions'] else 'Extract all relevant financial information'}

EXTRACTION PARAMETERS:
======================
Max Depth: {instructions['max_depth']}
Max Pages: {instructions['max_pages']}

YOUR TASK:
==========
1. Start by crawling each URL provided with the specified depth and page limits
2. Look for all the specified types of financial data
3. Process any PDF documents found
4. Extract and analyze financial-related links
5. Be thorough and systematic in your search
6. Provide a comprehensive summary of all financial information found

Begin by crawling the first URL with appropriate parameters.
"""
    
    # Create agent input with single key
    agent_input = {
        "input": consolidated_input
    }
    
    try:
        # Run the agent
        result = agent_executor.invoke(agent_input)
        
        # Save the results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results_file = f"extraction_results_{timestamp}.txt"
        
        with open(results_file, 'w', encoding='utf-8') as f:
            f.write("AUTONOMOUS FINANCIAL DATA EXTRACTION RESULTS\n")
            f.write("=" * 60 + "\n")
            f.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Instructions file: {instructions_file}\n")
            f.write("\nProcessed URLs:\n")
            for url in instructions['urls']:
                f.write(f"  • {url}\n")
            f.write("\n" + "=" * 60 + "\n")
            f.write("\nEXTRACTION RESULTS:\n")
            f.write("-" * 60 + "\n")
            f.write(result.get("output", "No results generated"))
        
        print("\n" + "=" * 80)
        print("✅ EXTRACTION COMPLETED")
        print(f"📁 Results saved to: {results_file}")
        print("=" * 80)
        
        # Also print the summary
        print("\n📊 EXTRACTION SUMMARY:")
        print("-" * 40)
        output_text = result.get("output", "No results generated")
        print(output_text[:2000])
        if len(output_text) > 2000:
            print(f"\n... (see {results_file} for complete results)")
        
    except Exception as e:
        print(f"\n❌ Error during extraction: {str(e)}")
        import traceback
        traceback.print_exc()

def create_sample_instructions_file():
    """Create a sample instructions file for users"""
    sample_content = """FINANCIAL DATA EXTRACTION INSTRUCTIONS
=======================================

Target Websites:
----------------
URL: https://cityofhodgenvilleky.com
URL: https://finance.lacity.gov

Data Requirements:
------------------
- Tax rates and schedules
- Business license fees
- Permit costs
- Property tax information
- Sales tax rates
- Utility rates
- Parking fees and fines
- Registration fees
- Assessment values

Extraction Parameters:
----------------------
Depth: 3
Pages: 50

Specific Instructions:
----------------------
1. Start from the main page and explore all financial-related sections
2. Pay special attention to PDF documents that might contain rate schedules
3. Look for pages with titles containing: tax, fee, rate, cost, budget, finance
4. Extract all numerical values with percentages or dollar amounts
5. Process any downloadable documents (PDFs, Excel files) found
6. Follow links to department pages (Treasury, Finance, Tax Collector)
7. Check for business and resident sections separately
8. Look for current year (2024-2025) information primarily

Additional Notes:
-----------------
- Focus on official government rates and fees
- Skip news articles and press releases
- Prioritize structured data tables and lists
- Save all rate schedules and fee tables found
"""
    
    filename = "extraction_instructions.txt"
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(sample_content)
    
    print(f"✅ Sample instructions file created: {filename}")
    return filename

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        # Use provided instructions file
        instructions_file = sys.argv[1]
    else:
        # Check if default instructions file exists
        if os.path.exists("extraction_instructions.txt"):
            instructions_file = "extraction_instructions.txt"
            print("📄 Using existing extraction_instructions.txt")
        else:
            # Create sample instructions file
            print("📝 No instructions file provided. Creating sample...")
            instructions_file = create_sample_instructions_file()
            print("\n⚠️  Please edit the instructions file with your specific requirements")
            print(f"📄 File location: {instructions_file}")
            print("\n🔄 Re-run the script after editing the instructions file")
            sys.exit(0)
    
    # Run the autonomous extraction
    run_autonomous_extraction(instructions_file)
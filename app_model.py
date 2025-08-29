import asyncio
import sys
import warnings
import nest_asyncio
from typing import Dict, List, Optional
from datetime import datetime
import os

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

# Tool Functions using the Enhanced Extractor
async def crawl_and_extract_financial_data(url: str, max_depth: int = 2, max_pages: int = 20) -> str:
    """
    Crawl a website and extract financial data (taxes, fees, rates, costs).
    Returns a summary of financial information found.
    """
    try:
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
                input_str.split(',')[0].strip(),
                int(input_str.split(',')[1].strip()) if ',' in input_str else 2,
                int(input_str.split(',')[2].strip()) if input_str.count(',') >= 2 else 20
            )
        ),
        description="Crawl a website recursively to extract financial data (taxes, fees, rates). Input: 'url' or 'url,max_depth,max_pages'. Example: 'https://example.com,3,50'"
    ),
    Tool(
        name="process_pdf",
        func=lambda pdf_url: asyncio.run(process_pdf_document(pdf_url)),
        description="Process a PDF document and extract text using OCR if needed. Input: PDF URL. Returns extracted text content."
    ),
    Tool(
        name="analyze_webpage",
        func=lambda url: asyncio.run(analyze_single_webpage(url)),
        description="Analyze a single webpage for financial information without recursive crawling. Input: webpage URL."
    ),
    Tool(
        name="extract_links",
        func=lambda url: asyncio.run(extract_links_from_page(url)),
        description="Extract all links from a webpage, categorized by type (PDFs, documents, financial). Input: webpage URL."
    )
]

# Create the React Agent Prompt Template
react_prompt = PromptTemplate.from_template("""You are an advanced Financial Data Extraction Agent with powerful web crawling and document processing capabilities.

Your expertise includes:
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

Continue this process until you have enough information, then provide your final answer:
```
Thought: I have gathered enough information to answer the question
Final Answer: [your comprehensive answer based on the observations]
```

Current conversation:
{chat_history}

Question: {input}
{agent_scratchpad}

Begin! Remember to be thorough and extract all relevant financial information.""")

# Create memory
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True
)

# Create the agent using create_react_agent
agent = create_react_agent(
    llm=llm,
    tools=tools,
    prompt=react_prompt
)

# Create the agent executor
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    memory=memory,
    verbose=True,
    max_iterations=5,
    handle_parsing_errors=True,
    early_stopping_method="generate"
)

def run_agent(query: str) -> str:
    """Run the agent with a query"""
    try:
        result = agent_executor.invoke({"input": query})
        return result.get("output", "No response generated")
    except Exception as e:
        return f"Error running agent: {str(e)}"

def interactive_chat():
    """Interactive chat with the Financial Data Extraction Agent"""
    print("=" * 80)
    print("🤖 FINANCIAL DATA EXTRACTION AGENT")
    print("=" * 80)
    print("Available capabilities:")
    print("  📊 Extract financial data from websites (taxes, fees, rates)")
    print("  📄 Process PDF documents with OCR support")
    print("  🔗 Extract and categorize links from webpages")
    print("  🌐 Recursively crawl websites for financial information")
    print("\nType 'help' for available commands, 'exit' to quit")
    print("-" * 80)
    
    while True:
        try:
            user_input = input("\n💬 You: ").strip()
            
            if user_input.lower() in ['exit', 'quit', 'bye']:
                print("\n👋 Goodbye!")
                break
            
            if user_input.lower() == 'help':
                print("\n📚 Available Tools:")
                for tool in tools:
                    print(f"  • {tool.name}: {tool.description}")
                print("\n💡 Example queries:")
                print("  - 'Crawl https://cityofhodgenvilleky.com and find all tax and fee information'")
                print("  - 'Process this PDF: https://example.com/document.pdf'")
                print("  - 'Extract all links from https://finance.lacity.gov'")
                print("  - 'Analyze https://example.com/taxes for financial data'")
                continue
            
            if not user_input:
                continue
            
            print("\n🤔 Agent is processing...")
            response = run_agent(user_input)
            
            print("\n🤖 Agent Response:")
            print("-" * 40)
            print(response)
            
        except KeyboardInterrupt:
            print("\n\n👋 Chat interrupted. Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")

if __name__ == "__main__":
    # Example: Run a specific query
    # result = run_agent("Crawl https://cityofhodgenvilleky.com and extract all financial information including PDFs")
    # print(result)
    
    # Or run interactive chat
    interactive_chat()
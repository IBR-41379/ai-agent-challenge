#!/usr/bin/env python3
"""
Agent-as-Coder: Autonomous Bank Statement PDF Parser Generator

This agent uses LangGraph to autonomously generate custom parsers for bank statement PDFs.
The workflow follows: Plan → Analyze PDF → Generate Parser → Run Tests → Fix Parser (up to 3 attempts) → Finalize
"""

import argparse
import os
import pdfplumber
import pandas as pd
import pytest
import subprocess
import sys
import importlib
import re
from typing import TypedDict, Optional, Dict, Any, List
from pathlib import Path

from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

load_dotenv()

# PDF Analyzer functions
def extract_pdf_structure(pdf_path: str) -> Dict[str, Any]:
    """
    Extract structural information from PDF bank statement.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dictionary containing:
        - raw_text: Full extracted text
        - pages: List of page texts
        - tables: List of extracted tables
        - metadata: PDF metadata
    """
    structure = {
        'raw_text': '',
        'pages': [],
        'tables': [],
        'metadata': {}
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        # Extract metadata
        structure['metadata'] = {
            'pages': len(pdf.pages),
            'title': pdf.metadata.get('Title', ''),
            'author': pdf.metadata.get('Author', ''),
            'subject': pdf.metadata.get('Subject', ''),
            'creator': pdf.metadata.get('Creator', '')
        }
        
        # Extract text from each page
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                structure['pages'].append(page_text)
                structure['raw_text'] += page_text + '\n'
            
            # Extract tables
            tables = page.extract_tables()
            if tables:
                structure['tables'].extend(tables)
    
    return structure

def analyze_table_structure(tables: List[List[List[str]]]) -> Dict[str, Any]:
    """
    Analyze the structure of extracted tables to identify transaction data.
    
    Args:
        tables: List of tables extracted from PDF
        
    Returns:
        Dictionary with table analysis
    """
    analysis = {
        'table_count': len(tables),
        'potential_transaction_tables': [],
        'column_patterns': []
    }
    
    for i, table in enumerate(tables):
        if not table:
            continue
            
        # Check if this looks like a transaction table
        headers = table[0] if table else []
        row_count = len(table)
        
        # Look for common banking columns
        banking_keywords = ['date', 'description', 'debit', 'credit', 'balance', 'amount', 'transaction']
        header_text = ' '.join([str(h).lower() for h in headers if h])
        
        score = sum(1 for keyword in banking_keywords if keyword in header_text)
        
        if score >= 2 and row_count > 1:
            analysis['potential_transaction_tables'].append({
                'table_index': i,
                'headers': headers,
                'row_count': row_count,
                'banking_score': score
            })
    
    return analysis

def get_pdf_analysis(pdf_path: str) -> Dict[str, Any]:
    """
    Complete PDF analysis for parser generation.
    
    Args:
        pdf_path: Path to PDF
        
    Returns:
        Comprehensive analysis dictionary
    """
    structure = extract_pdf_structure(pdf_path)
    table_analysis = analyze_table_structure(structure['tables'])
    
    return {
        'structure': structure,
        'table_analysis': table_analysis,
        'summary': {
            'total_pages': len(structure['pages']),
            'total_tables': len(structure['tables']),
            'text_length': len(structure['raw_text']),
            'potential_transaction_tables': len(table_analysis['potential_transaction_tables'])
        }
    }

# Parser Generator class and functions
class ParserGenerator:
    def __init__(self):
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain.prompts import PromptTemplate
        from langchain.chains import LLMChain
        
        # Get model from environment variable with fallback
        model_name = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash-lite")
        
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            api_key=os.getenv("GOOGLE_API_KEY"),
            temperature=0.1
        )
        
        self.generation_prompt = PromptTemplate(
            input_variables=["bank_name", "pdf_analysis", "expected_csv_sample", "expected_columns", "error_context"],
            template="""
You are an expert Python developer specializing in PDF parsing for bank statements. Generate a complete, working Python function to parse a bank statement PDF.

Bank: {bank_name}
PDF Analysis: {pdf_analysis}
Expected CSV Sample (first 5 rows):
{expected_csv_sample}
Expected Columns: {expected_columns}

{error_context}

Requirements:
1. Use pdfplumber for PDF text/table extraction
2. Return a pandas DataFrame with exactly these columns: {expected_columns}
3. Handle date parsing appropriately - KEEP DATES AS STRINGS in 'DD-MM-YYYY' format (e.g., '01-08-2024'), do NOT convert to datetime objects
4. Clean and normalize the data
5. Include proper error handling
6. Add docstring with description
7. CRITICAL: Bank statements split transactions across multiple tables/pages. You MUST combine ALL transaction tables into a single DataFrame.
8. Look for tables with banking-related headers (Date, Description, Debit, Credit, Balance)
9. Skip header rows and combine data from ALL relevant tables to get exactly 100 rows
10. CRITICAL: Use pandas NaN (pd.NaN or numpy.nan) for missing values, NOT None values
11. For numeric columns (Debit Amt, Credit Amt, Balance), use pd.to_numeric() with errors='coerce' to convert and handle NaN properly
12. Ensure the output DataFrame exactly matches the expected CSV format including NaN handling

CRITICAL IMPORT REQUIREMENTS:
- Always import numpy as np (not pd.np)
- Use np.nan for NaN values
- Import: import pdfplumber, import pandas as pd, import numpy as np

Function signature:
def parse(pdf_path: str) -> pd.DataFrame:

IMPORTANT: Generate ONLY the complete Python function code with proper imports. Do NOT include any markdown formatting, code blocks, or explanations. Start directly with the imports and function definition.
"""
        )
        
        # Use modern RunnableSequence instead of deprecated LLMChain
        self.chain = self.generation_prompt | self.llm

    def generate_parser_code(self, bank_name: str, pdf_analysis: Dict[str, Any], expected_csv_path: str, error_details: Optional[Dict[str, Any]] = None) -> str:
        """
        Generate parser code for the given bank.
        
        Args:
            bank_name: Name of the bank (e.g., 'icici')
            pdf_analysis: Analysis from pdf_analyzer.get_pdf_analysis()
            expected_csv_path: Path to expected CSV for reference
            error_details: Optional error information from previous failed attempts
            
        Returns:
            Generated Python code for the parser function
        """
        # Load expected CSV sample
        expected_df = pd.read_csv(expected_csv_path)
        expected_columns = list(expected_df.columns)
        sample_data = expected_df.head(5).to_string()
        
        # Prepare PDF analysis summary
        analysis_summary = f"""
Total pages: {pdf_analysis['summary']['total_pages']}
Total tables: {pdf_analysis['summary']['total_tables']}
Text length: {pdf_analysis['summary']['text_length']}
Potential transaction tables: {pdf_analysis['summary']['potential_transaction_tables']}

Raw text preview (first 500 chars):
{pdf_analysis['structure']['raw_text'][:500]}...

Table analysis:
{pdf_analysis['table_analysis']}
"""
        
        # Add error context if available
        error_context = ""
        if error_details:
            test_error = error_details.get('test_error', 'Unknown')
            comparison_details = error_details.get('comparison_details', {})
            attempt_number = error_details.get('attempt_number', 1)
            
            error_context = f"""
PREVIOUS ATTEMPT {attempt_number} FAILED with these specific errors that must be fixed:

Test Error: {test_error}

DETAILED ERROR ANALYSIS:
"""
            
            # Add specific error details from comparison
            if 'nan_handling_issues' in comparison_details and comparison_details['nan_handling_issues']:
                error_context += f"""
NaN HANDLING ISSUES:
{chr(10).join(comparison_details['nan_handling_issues'])}

CRITICAL FIX: Use pandas NaN (pd.NaN or numpy.nan) instead of None values. 
For empty cells, use: pd.to_numeric(value, errors='coerce') which converts empty/invalid to NaN.
"""
            
            if 'data_type_issues' in comparison_details and comparison_details['data_type_issues']:
                error_context += f"""
DATA TYPE ISSUES:
{chr(10).join(comparison_details['data_type_issues'])}
"""
            
            if 'value_format_issues' in comparison_details and comparison_details['value_format_issues']:
                error_context += f"""
VALUE FORMAT ISSUES:
{chr(10).join(comparison_details['value_format_issues'])}
"""
            
            if 'differences' in comparison_details and comparison_details['differences']:
                error_context += f"""
SPECIFIC DIFFERENCES FOUND:
{chr(10).join(comparison_details['differences'][:5])}  # Show only first 5 for brevity
"""
            
            error_context += f"""

CRITICAL FIXES REQUIRED FOR ATTEMPT {attempt_number + 1}:
1. MUST use pandas NaN (pd.NaN or np.nan) for missing values, NOT None
2. For numeric columns: use pd.to_numeric(column, errors='coerce') 
3. Ensure dates stay as strings in 'DD-MM-YYYY' format
4. Combine ALL transaction tables from the PDF
5. Return exactly 100 rows
6. Match the exact output format of the expected CSV
7. IMPORT CORRECTLY: import numpy as np (not pd.np), import pandas as pd, import pdfplumber

COMMON FIXES:
- If getting "module 'pandas' has no attribute 'np'" error: Import numpy separately as 'import numpy as np'
- If getting empty DataFrame: Check table extraction logic and header matching
- If getting wrong NaN values: Use np.nan instead of None

Please analyze the error details above and generate a corrected parser that addresses these specific issues.
"""
        
        # Prepare prompt input
        prompt_input = {
            "bank_name": bank_name.upper(),
            "pdf_analysis": analysis_summary,
            "expected_csv_sample": sample_data,
            "expected_columns": expected_columns,
            "error_context": error_context
        }
        
        # Generate code using Gemini
        result = self.chain.invoke(prompt_input)
        
        # Debug: Print the raw LLM response
        debug_print("\n" + "="*80)
        debug_print("🤖 DEBUG: RAW LLM RESPONSE")
        debug_print("="*80)
        debug_print(f"Response type: {type(result)}")
        debug_print(f"Response content (first 1000 chars):")
        debug_print(repr(result.content[:1000]))
        debug_print("="*80)
        
        # Extract content from AIMessage
        code = result.content.strip()
        
        # Clean the response - remove markdown code blocks if present
        if code.startswith('```python'):
            code = code[9:]  # Remove ```python
        if code.startswith('```'):
            code = code[3:]  # Remove ```
        if code.endswith('```'):
            code = code[:-3]  # Remove trailing ```
        code = code.strip()
        
        # Debug: Print the cleaned code
        debug_print("\n" + "="*80)
        debug_print("🔧 DEBUG: CLEANED PARSER CODE")
        debug_print("="*80)
        debug_print(f"Code length: {len(code)} characters")
        debug_print("First 500 characters of cleaned code:")
        debug_print(code[:500])
        debug_print("="*80)
        
        return code

def generate_parser_for_bank(bank_name: str, pdf_path: str, csv_path: str, error_details: Optional[Dict[str, Any]] = None) -> str:
    """
    Convenience function to generate parser code for a bank.
    
    Args:
        bank_name: Bank name (e.g., 'icici')
        pdf_path: Path to sample PDF
        csv_path: Path to expected CSV
        error_details: Optional error information from previous failed attempts
        
    Returns:
        Generated parser code
    """
    debug_print(f"🔍 DEBUG: generate_parser_for_bank() called")
    debug_print(f"🔍 DEBUG: bank_name={bank_name}, pdf_path={pdf_path}, csv_path={csv_path}")
    debug_print(f"🔍 DEBUG: error_details={'provided' if error_details else 'None'}")
    
    analysis = get_pdf_analysis(pdf_path)
    debug_print(f"🔍 DEBUG: PDF analysis completed, found {analysis['summary']['total_tables']} tables")
    
    generator = ParserGenerator()
    debug_print(f"🔍 DEBUG: ParserGenerator instance created, calling generate_parser_code()...")
    
    code = generator.generate_parser_code(bank_name, analysis, csv_path, error_details)
    
    debug_print(f"🔍 DEBUG: generate_parser_code() returned {len(code)} characters")
    
    return code

# Test Runner functions
def run_parser_test(bank_name: str, parser_module_path: str, pdf_path: str, expected_csv_path: str) -> Dict[str, Any]:
    """
    Run automated test for a generated parser with enhanced error reporting.
    
    Args:
        bank_name: Name of the bank (e.g., 'icici')
        parser_module_path: Path to the parser module (e.g., 'custom_parsers.icici_parser')
        pdf_path: Path to test PDF
        expected_csv_path: Path to expected CSV
        
    Returns:
        Dictionary with test results and detailed error information
    """
    result = {
        'success': False,
        'error': None,
        'details': {},
        'execution_error': None,
        'import_error': None
    }
    
    try:
        # Import the parser module dynamically
        module_name = parser_module_path.replace('/', '.').replace('.py', '')
        if module_name.startswith('custom_parsers.'):
            module_name = module_name
        else:
            module_name = f"custom_parsers.{bank_name}_parser"
        
        # Clear any cached imports to ensure we get the latest version
        import importlib
        if module_name in sys.modules:
            importlib.reload(sys.modules[module_name])
        
        try:
            # Import the module
            parser_module = importlib.import_module(module_name)
        except Exception as e:
            result['import_error'] = str(e)
            result['error'] = f"Import failed: {str(e)}"
            return result
        
        # Check if parse function exists
        if not hasattr(parser_module, 'parse'):
            result['error'] = "Parser module does not have a 'parse' function"
            return result
        
        try:
            # Run the parse function
            actual_df = parser_module.parse(pdf_path)
        except Exception as e:
            result['execution_error'] = str(e)
            result['error'] = f"Parser execution failed: {str(e)}"
            return result
        
        # Validate return type
        if not isinstance(actual_df, pd.DataFrame):
            result['error'] = f"Parser returned {type(actual_df)}, expected pandas.DataFrame"
            return result
        
        # Load expected CSV
        try:
            expected_df = pd.read_csv(expected_csv_path)
        except Exception as e:
            result['error'] = f"Failed to load expected CSV: {str(e)}"
            return result
        
        # Compare DataFrames
        result['details'] = compare_dataframes(actual_df, expected_df)
        
        if result['details']['match']:
            result['success'] = True
        else:
            result['error'] = f"DataFrame mismatch: {result['details']['differences']}"
            
    except Exception as e:
        result['error'] = f"Unexpected error: {str(e)}"
        result['details']['exception'] = str(e)
    
    return result

def compare_dataframes(actual: pd.DataFrame, expected: pd.DataFrame) -> Dict[str, Any]:
    """
    Compare two DataFrames and return detailed comparison with enhanced debugging.
    
    Args:
        actual: DataFrame from parser
        expected: Expected DataFrame from CSV
        
    Returns:
        Dictionary with comparison results and detailed analysis
    """
    comparison = {
        'match': False,
        'differences': [],
        'actual_shape': actual.shape,
        'expected_shape': expected.shape,
        'actual_columns': list(actual.columns),
        'expected_columns': list(expected.columns),
        'data_type_issues': [],
        'nan_handling_issues': [],
        'value_format_issues': []
    }
    
    # Check columns
    if set(actual.columns) != set(expected.columns):
        comparison['differences'].append(f"Column mismatch. Actual: {actual.columns.tolist()}, Expected: {expected.columns.tolist()}")
        return comparison
    
    # Check shapes
    if actual.shape != expected.shape:
        comparison['differences'].append(f"Shape mismatch. Actual: {actual.shape}, Expected: {expected.shape}")
        return comparison
    
    # Enhanced comparison with detailed analysis
    for col in expected.columns:
        if col not in actual.columns:
            comparison['differences'].append(f"Missing column: {col}")
            continue
            
        actual_col = actual[col]
        expected_col = expected[col]
        
        # Check for NaN handling issues
        actual_na_mask = pd.isna(actual_col)
        expected_na_mask = pd.isna(expected_col)
        
        if not actual_na_mask.equals(expected_na_mask):
            na_diff_count = (actual_na_mask != expected_na_mask).sum()
            comparison['nan_handling_issues'].append(f"Column '{col}' has {na_diff_count} NaN differences")
            
            # Find specific NaN issues
            actual_none_mask = actual_col.isnull() & (actual_col.astype(str) == 'None')
            if actual_none_mask.any():
                comparison['nan_handling_issues'].append(f"Column '{col}' uses None instead of NaN in {actual_none_mask.sum()} rows")
        
        # Data type comparison
        if actual_col.dtype != expected_col.dtype:
            comparison['data_type_issues'].append(f"Column '{col}' dtype mismatch: actual={actual_col.dtype}, expected={expected_col.dtype}")
        
        # Value comparison (handle both numeric and string columns)
        try:
            if col in ['Debit Amt', 'Credit Amt', 'Balance']:
                # For numeric columns, handle NaN specially
                actual_filled = actual_col.fillna(-999999)  # Use unique value for comparison
                expected_filled = expected_col.fillna(-999999)
                
                if not actual_filled.equals(expected_filled):
                    diff_mask = actual_filled != expected_filled
                    diff_count = diff_mask.sum()
                    comparison['differences'].append(f"Column '{col}' has {diff_count} value differences")
                    
                    # Show first few differences
                    if diff_mask.any():
                        first_diff_idx = diff_mask.idxmax()
                        actual_val = actual_col.iloc[first_diff_idx]
                        expected_val = expected_col.iloc[first_diff_idx]
                        comparison['differences'].append(
                            f"First difference in '{col}': actual='{actual_val}', expected='{expected_val}'"
                        )
            else:
                # For string columns
                actual_str = actual_col.astype(str).fillna('__NA__')
                expected_str = expected_col.astype(str).fillna('__NA__')
                
                if not actual_str.equals(expected_str):
                    diff_mask = actual_str != expected_str
                    diff_count = diff_mask.sum()
                    comparison['differences'].append(f"Column '{col}' has {diff_count} differences")
                    
                    # Show first few differences
                    if diff_mask.any():
                        first_diff_idx = diff_mask.idxmax()
                        comparison['differences'].append(
                            f"First difference in '{col}': actual='{actual_str.iloc[first_diff_idx]}', expected='{expected_str.iloc[first_diff_idx]}'"
                        )
        except Exception as e:
            comparison['differences'].append(f"Error comparing column '{col}': {str(e)}")
    
    # Try DataFrame.equals as final check
    try:
        if actual.equals(expected):
            comparison['match'] = True
            comparison['differences'] = []  # Clear differences if equals passes
    except Exception as e:
        comparison['differences'].append(f"DataFrame.equals failed: {str(e)}")
    
    return comparison

def run_pytest_suite(test_dir: str = "tests") -> Dict[str, Any]:
    """
    Run the full pytest suite.
    
    Args:
        test_dir: Directory containing test files
        
    Returns:
        Dictionary with pytest results
    """
    result = {
        'success': False,
        'output': '',
        'error': None
    }
    
    try:
        # Run pytest programmatically
        cmd = [sys.executable, "-m", "pytest", test_dir, "-v", "--tb=short"]
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        
        result['output'] = process.stdout
        if process.stderr:
            result['output'] += "\nSTDERR:\n" + process.stderr
            
        result['success'] = process.returncode == 0
        
        if not result['success']:
            result['error'] = f"Pytest failed with return code {process.returncode}"
            
    except Exception as e:
        result['error'] = str(e)
    
    return result

class AgentState(TypedDict):
    """State for the LangGraph workflow"""
    target_bank: str
    pdf_path: str
    csv_path: str
    parser_code: Optional[str]
    parser_file_path: str
    test_results: Optional[Dict[str, Any]]
    attempts: int
    max_attempts: int
    success: bool
    error_message: Optional[str]
    verbose: bool

# Global verbose flag for debug printing
_VERBOSE_MODE = False

def debug_print(message: str):
    """Print debug message only if verbose mode is enabled"""
    if _VERBOSE_MODE:
        print(message)

def set_verbose_mode(verbose: bool):
    """Set global verbose mode"""
    global _VERBOSE_MODE
    _VERBOSE_MODE = verbose
    success: bool
    error_message: Optional[str]

def plan_node(state: AgentState) -> AgentState:
    """Plan node: Validate inputs and set up the workflow"""
    print("🔍 Planning phase...")
    
    # Set global verbose mode
    set_verbose_mode(state.get('verbose', False))
    
    bank = state['target_bank']
    pdf_path = f"data/{bank}/{bank} sample.pdf"
    csv_path = f"data/{bank}/result.csv"
    parser_file_path = f"custom_parsers/{bank}_parser.py"
    
    # Validate inputs
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    
    # Ensure custom_parsers directory exists
    Path("custom_parsers").mkdir(exist_ok=True)
    
    state.update({
        'pdf_path': pdf_path,
        'csv_path': csv_path,
        'parser_file_path': parser_file_path,
        'attempts': 0,
        'max_attempts': 3,
        'success': False,
        'error_message': None
    })
    
    print(f"✅ Planning complete for {bank.upper()}")
    return state

def analyze_pdf_node(state: AgentState) -> AgentState:
    """Analyze PDF node: Extract structure from PDF"""
    print("📊 Analyzing PDF structure...")
    
    try:
        analysis = get_pdf_analysis(state['pdf_path'])
        state['pdf_analysis'] = analysis
        print(f"✅ PDF analysis complete: {analysis['summary']['total_pages']} pages, {analysis['summary']['total_tables']} tables")
    except Exception as e:
        state['error_message'] = f"PDF analysis failed: {str(e)}"
        print(f"❌ PDF analysis failed: {str(e)}")
    
    return state

def generate_parser_node(state: AgentState) -> AgentState:
    """Generate Parser node: Use LLM to generate custom parsing code"""
    print("🤖 Generating parser code...")
    debug_print(f"🔍 DEBUG: This is attempt #{state['attempts'] + 1}")
    debug_print(f"🔍 DEBUG: Target bank: {state['target_bank']}")
    
    try:
        debug_print(f"🔍 DEBUG: Calling generate_parser_for_bank() with error_details=None (initial generation)")
        code = generate_parser_for_bank(
            state['target_bank'],
            state['pdf_path'],
            state['csv_path']
        )
        
        debug_print(f"🔍 DEBUG: Received code from LLM, length: {len(code)} characters")
        debug_print(f"🔍 DEBUG: Code starts with: {repr(code[:100])}")
        
        # Write the code to file
        with open(state['parser_file_path'], 'w') as f:
            f.write(code)
        
        state['parser_code'] = code
        state['attempts'] += 1
        state['error_message'] = None  # Clear any previous error
        
        print(f"✅ Parser code generated and saved to {state['parser_file_path']}")
        
    except Exception as e:
        state['error_message'] = f"Parser generation failed: {str(e)}"
        print(f"❌ Parser generation failed: {str(e)}")
    
    return state

def run_tests_node(state: AgentState) -> AgentState:
    """Run Tests node: Validate the generated parser with detailed feedback"""
    print("🧪 Running tests...")
    
    try:
        test_results = run_parser_test(
            state['target_bank'],
            f"custom_parsers.{state['target_bank']}_parser",
            state['pdf_path'],
            state['csv_path']
        )
        
        state['test_results'] = test_results
        
        if test_results['success']:
            state['success'] = True
            print("✅ Tests passed!")
        else:
            error_msg = test_results.get('error', 'Unknown error')
            print(f"❌ Tests failed: {error_msg}")
            
            # Add detailed error information for debugging
            if 'details' in test_results:
                details = test_results['details']
                if 'nan_handling_issues' in details and details['nan_handling_issues']:
                    print(f"   📋 NaN handling issues: {len(details['nan_handling_issues'])} found")
                if 'data_type_issues' in details and details['data_type_issues']:
                    print(f"   📋 Data type issues: {len(details['data_type_issues'])} found")
                if 'differences' in details and details['differences']:
                    print(f"   📋 Value differences: {len(details['differences'])} found")
                    # Show first difference for debugging
                    if details['differences']:
                        print(f"   🔍 First difference: {details['differences'][0]}")
            
    except Exception as e:
        state['error_message'] = f"Test execution failed: {str(e)}"
        print(f"❌ Test execution failed: {str(e)}")
    
    return state

def fix_parser_node(state: AgentState) -> AgentState:
    """Fix Parser node: Attempt to fix the parser based on detailed test failures"""
    print(f"🔧 Fixing parser (attempt {state['attempts'] + 1}/{state['max_attempts']})...")
    
    if state['test_results'] and not state['test_results']['success']:
        # Prepare comprehensive error details for the LLM
        error_details = {
            'test_error': state['test_results'].get('error', 'Unknown error'),
            'comparison_details': state['test_results'].get('details', {}),
            'attempt_number': state['attempts']
        }
        
        # Log the specific issues we're trying to fix
        details = error_details['comparison_details']
        if details:
            print(f"   🔍 Fixing based on:")
            if 'nan_handling_issues' in details and details['nan_handling_issues']:
                print(f"      - NaN handling issues: {len(details['nan_handling_issues'])}")
            if 'data_type_issues' in details and details['data_type_issues']:
                print(f"      - Data type mismatches: {len(details['data_type_issues'])}")
            if 'differences' in details and details['differences']:
                print(f"      - Value differences: {len(details['differences'])}")
        
        debug_print(f"🔍 DEBUG: Calling generate_parser_for_bank() with error_details for fixing")
        debug_print(f"🔍 DEBUG: Error details being passed: {error_details}")
        
        # Generate parser with detailed error context
        try:
            code = generate_parser_for_bank(
                state['target_bank'],
                state['pdf_path'],
                state['csv_path'],
                error_details
            )
            
            debug_print(f"🔍 DEBUG: Received fixed code from LLM, length: {len(code)} characters")
            debug_print(f"🔍 DEBUG: Fixed code starts with: {repr(code[:100])}")
            
            # Write the code to file
            with open(state['parser_file_path'], 'w') as f:
                f.write(code)
            
            state['parser_code'] = code
            state['attempts'] += 1
            state['error_message'] = None  # Clear any previous error
            
            print(f"✅ Fixed parser code generated and saved to {state['parser_file_path']}")
            
        except Exception as e:
            state['error_message'] = f"Parser fix generation failed: {str(e)}"
            print(f"❌ Parser fix generation failed: {str(e)}")
    else:
        print("⚠️  No test results available for fixing")
    
    return state

def finalize_node(state: AgentState) -> AgentState:
    """Finalize node: Complete the process with detailed reporting"""
    if state['success']:
        print("🎉 Parser generation successful!")
        print(f"📁 Generated parser: {state['parser_file_path']}")
        print(f"📊 Total attempts: {state['attempts']}")
        print("🧪 Parser passed all tests!")
        
        # Additional validation
        try:
            # Quick validation that the parser file exists and is importable
            import importlib.util
            spec = importlib.util.spec_from_file_location("test_parser", state['parser_file_path'])
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            if hasattr(module, 'parse'):
                print("✅ Parser module is importable and has parse function")
            else:
                print("⚠️  Warning: Parser module missing parse function")
        except Exception as e:
            print(f"⚠️  Warning: Parser validation failed: {str(e)}")
    else:
        print("💥 Parser generation failed after maximum attempts")
        print(f"📊 Total attempts: {state['attempts']}/{state['max_attempts']}")
        
        if state.get('error_message'):
            print(f"🔴 Final error: {state['error_message']}")
        
        if state.get('test_results') and not state['test_results']['success']:
            print("🔍 Last test failure details:")
            test_error = state['test_results'].get('error', 'Unknown')
            print(f"   Error: {test_error}")
            
            details = state['test_results'].get('details', {})
            if 'differences' in details and details['differences']:
                print(f"   Main issues: {details['differences'][:3]}")  # Show first 3 issues
        
        print("\n💡 Troubleshooting tips:")
        print("   1. Check PDF structure with: python -c 'import pdfplumber; print(pdfplumber.open(\"data/icici/icici sample.pdf\").pages[0].extract_tables())'")
        print("   2. Verify expected CSV format matches actual data")
        print("   3. Increase max_attempts if needed")
        print("   4. Check API key and network connectivity")
    
    return state

def should_retry(state: AgentState) -> str:
    """Conditional edge: Decide whether to retry or finalize with improved logic"""
    # If successful, always finalize
    if state['success']:
        return "finalize"
    
    # If there was an error in generation (not just test failure), stop
    if state.get('error_message'):
        print(f"🛑 Stopping due to generation error: {state['error_message']}")
        return "finalize"
    
    # If we've exceeded attempts, stop
    if state['attempts'] >= state['max_attempts']:
        print(f"🛑 Stopping after {state['max_attempts']} attempts")
        return "finalize"
    
    # If tests failed but generation was successful, try to fix
    if state['test_results'] and not state['test_results']['success']:
        remaining_attempts = state['max_attempts'] - state['attempts']
        print(f"🔄 Will retry - {remaining_attempts} attempts remaining")
        return "fix_parser"
    
    # Default case - shouldn't happen but be safe
    print("🛑 Unexpected state - finalizing")
    return "finalize"

def create_agent_workflow() -> StateGraph:
    """Create the LangGraph workflow"""
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("plan", plan_node)
    workflow.add_node("analyze_pdf", analyze_pdf_node)
    workflow.add_node("generate_parser", generate_parser_node)
    workflow.add_node("run_tests", run_tests_node)
    workflow.add_node("fix_parser", fix_parser_node)
    workflow.add_node("finalize", finalize_node)
    
    # Add edges
    workflow.add_edge("plan", "analyze_pdf")
    workflow.add_edge("analyze_pdf", "generate_parser")
    workflow.add_edge("generate_parser", "run_tests")
    workflow.add_edge("fix_parser", "run_tests")
    workflow.add_edge("finalize", END)
    
    # Add conditional edge
    workflow.add_conditional_edges(
        "run_tests",
        should_retry,
        {
            "fix_parser": "fix_parser",
            "finalize": "finalize"
        }
    )
    
    # Set entry point
    workflow.set_entry_point("plan")
    
    return workflow

def main():
    """Main function with enhanced error handling and logging"""
    parser = argparse.ArgumentParser(description="Generate bank statement PDF parsers autonomously")
    parser.add_argument("--target", required=True, help="Target bank name (e.g., icici)")
    parser.add_argument("--max-attempts", type=int, default=3, help="Maximum fix attempts (default: 3)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    # Check for API key
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ Error: GOOGLE_API_KEY environment variable not set")
        print("Please set your Google Gemini API key in .env file")
        print("Get your API key from: https://makersuite.google.com/app/apikey")
        return 1
    
    # Validate target bank data exists
    target_bank = args.target.lower()
    pdf_path = f"data/{target_bank}/{target_bank} sample.pdf"
    csv_path = f"data/{target_bank}/result.csv"
    
    if not os.path.exists(pdf_path):
        print(f"❌ Error: PDF file not found: {pdf_path}")
        print(f"Please ensure the sample PDF exists for {target_bank} bank")
        return 1
        
    if not os.path.exists(csv_path):
        print(f"❌ Error: Expected CSV file not found: {csv_path}")
        print(f"Please ensure the expected result CSV exists for {target_bank} bank")
        return 1
    
    print(f"🚀 Starting Agent-as-Coder for {args.target.upper()} bank")
    model_name = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash-lite")
    print(f"📊 Configuration: max_attempts={args.max_attempts}, verbose={args.verbose}, model={model_name}")
    
    # Initialize workflow
    try:
        workflow = create_agent_workflow()
        app = workflow.compile()
    except Exception as e:
        print(f"❌ Failed to initialize workflow: {str(e)}")
        return 1
    
    # Initial state
    initial_state: AgentState = {
        'target_bank': target_bank,
        'pdf_path': '',
        'csv_path': '',
        'parser_code': None,
        'parser_file_path': '',
        'test_results': None,
        'attempts': 0,
        'max_attempts': args.max_attempts,
        'success': False,
        'error_message': None,
        'verbose': args.verbose
    }
    
    # Run the workflow
    try:
        final_state = app.invoke(initial_state)
        
        if final_state['success']:
            print("\n✅ SUCCESS: Parser generated successfully!")
            print(f"📁 Parser file: {final_state['parser_file_path']}")
            print("🧪 Run 'pytest tests/' to verify the parser")
            print(f"🎯 Or test directly: python -c \"from custom_parsers.{target_bank}_parser import parse; print(parse('{pdf_path}'))\"")
            return 0
        else:
            print("\n❌ FAILED: Could not generate working parser")
            if final_state.get('error_message'):
                print(f"Error: {final_state['error_message']}")
            return 1
                
    except KeyboardInterrupt:
        print("\n⏹️  Process interrupted by user")
        return 1
    except Exception as e:
        print(f"\n💥 Workflow execution failed: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1

if __name__ == "__main__":
    exit(main())
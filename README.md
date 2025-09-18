# Agent-as-Coder: Bank Statement PDF Parser Generator

An autonomous AI agent that generates custom parsers for bank statement PDFs using LangGraph. The agent follows a plan → generate → test → self-fix loop to create robust parsers that extract structured data from PDF statements.

## 🚀 Quick Start (5 Steps)

1. **Clone and Setup**
   ```bash
   git clone https://github.com/your-username/ai-agent-challenge.git
   cd ai-agent-challenge
   pip install -r requirements.txt
   ```

2. **Configure API Keys**
   ```bash
   cp .env.example .env
   # Edit .env and add your Google Gemini API key
   ```

3. **Generate ICICI Parser**
   ```bash
   python agent.py --target icici
   ```

4. **Run Tests**
   ```bash
   pytest tests/ -v
   ```

5. **Verify Generated Parser**
   ```bash
   python -c "from custom_parsers.icici_parser import parse; print(parse('data/icici/icici sample.pdf').head())"
   ```

## 🏗️ Agent Architecture

The agent uses a **LangGraph-based workflow** with six interconnected nodes that autonomously generate, test, and fix PDF parsers through an intelligent feedback loop:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Agent-as-Coder Workflow                           │
└─────────────────────────────────────────────────────────────────────────────┘

    INPUT: python agent.py --target icici
         │
         ▼
    ┌─────────┐    ┌──────────────┐    ┌─────────────────┐
    │  PLAN   │───▶│ ANALYZE PDF  │───▶│ GENERATE PARSER │
    │         │    │              │    │                 │
    │• Validate│    │• Extract     │    │• LLM prompts    │
    │  inputs  │    │  structure   │    │• Generate code  │
    │• Setup   │    │• Find tables │    │• Save to .py    │
    │  paths   │    │• Analyze     │    │                 │
    └─────────┘    │  metadata    │    └─────────────────┘
                   └──────────────┘             │
                                                ▼
    ┌─────────┐    ┌──────────────┐    ┌─────────────────┐
    │FINALIZE │◀───│  RUN TESTS   │◀───│   ATTEMPT #1    │
    │         │    │              │    │                 │
    │• Report │    │• Import      │    │                 │
    │  success│    │  parser      │    │                 │
    │• Show   │    │• Execute     │    │                 │
    │  results│    │  parse()     │    │                 │
    └─────────┘    │• DataFrame   │    └─────────────────┘
         ▲         │  .equals()   │             │
         │         └──────────────┘             │
         │                  │                  │
         │                  ▼                  ▼
         │         ┌─────────────────┐   ✅ PASS ❌ FAIL
         │         │   SUCCESS?      │         │
         │         │                 │         │
         │         │ Tests passed?   │         ▼
         │         │ Max attempts?   │   ┌─────────────────┐
         │         └─────────────────┘   │  FIX PARSER     │
         │                  │           │                 │
         │ ✅ SUCCESS        │           │• Analyze errors │
         │ ❌ MAX ATTEMPTS   │           │• Enhanced LLM   │
         │ 🚫 GENERATION     │           │  prompt with    │
         │    ERROR          │           │  error context  │
         └───────────────────┘           │• Generate fix   │
                                        │• Enhanced LLM   │
                                        │  prompt with    │
                                        │  error context  │
                                        │• Generate fix   │
                                        └─────────────────┘
                                                 │
                                                 ▼
                                        ┌─────────────────┐
                                        │   ATTEMPT #2    │
                                        │   ATTEMPT #3    │
                                        │  (MAX 3 TOTAL)  │
                                        └─────────────────┘
                                                 │
                                                 ▼
                                         BACK TO RUN TESTS

OUTPUT: custom_parsers/icici_parser.py with parse(pdf_path) -> DataFrame
```

**Key Features:**
- **State-Driven**: Each node updates `AgentState` with results and error context
- **Self-Correcting**: Failed tests trigger enhanced LLM prompts with specific error details  
- **Autonomous**: No human intervention required - handles edge cases automatically
- **Bounded**: Maximum 3 fix attempts prevents infinite loops
- **Always Finalizes**: Whether success or failure, generates comprehensive report

## 📁 Project Structure

```
ai-agent-challenge/
├── agent.py                 # Main agent orchestrator
├── pdf_analyzer.py          # PDF structure analysis
├── parser_generator.py      # LLM-based code generation
├── test_runner.py          # Automated testing framework
├── custom_parsers/         # Generated parser modules
│   └── icici_parser.py     # ICICI bank parser (generated)
├── tests/                  # Test suite
│   ├── test_icici_parser.py
│   └── test_agent.py
├── data/                   # Sample data
│   └── icici/
│       ├── icici sample.pdf
│       └── result.csv
└── requirements.txt
```

## 🎯 Features

### Core Capabilities
- **Autonomous Parser Generation**: Creates custom parsers without manual intervention
- **Multi-Library PDF Analysis**: Uses pdfplumber, PyPDF2, and pattern matching
- **Self-Correction Loop**: Automatically fixes parsing issues up to 3 attempts
- **Comprehensive Testing**: Validates schema, data types, and exact output matching
- **Error Recovery**: Graceful handling of edge cases and parsing failures

### Parser Contract
All generated parsers implement the standard interface:
```python
def parse(pdf_path: str) -> pd.DataFrame:
    """
    Parse bank statement PDF and return structured data
    
    Returns:
        DataFrame with columns: Date, Description, Debit Amt, Credit Amt, Balance
    """
```

### Supported Banks
- **ICICI Bank** (primary implementation)
- **Extensible Framework** for additional banks (SBI, HDFC, etc.)

## 🔧 Usage

### Basic Usage
```bash
python agent.py --target icici
```

### Advanced Options
```bash
python agent.py --target icici --max-attempts 5 --verbose
```

### Model Configuration
Configure the LLM model via environment variables:
```bash
# Use faster model
GOOGLE_MODEL=gemini-1.5-flash python agent.py --target icici

# Use more capable model
GOOGLE_MODEL=gemini-1.5-pro python agent.py --target icici
```

### CLI Arguments
- `--target`: Target bank name (required)
- `--max-attempts`: Maximum correction attempts (default: 3)
- `--verbose` / `-v`: Enable verbose logging and debug output

## 🧪 Testing

### Run All Tests
```bash
pytest tests/ -v
```

### Test Specific Parser
```bash
pytest tests/test_icici_parser.py -v
```

### Test Categories
- **Parser Generation**: Validates file creation and function signatures
- **Schema Compliance**: Ensures correct column names and data types
- **Data Accuracy**: Compares output with expected CSV using DataFrame.equals()
- **Error Handling**: Tests graceful failure modes

## 🤖 Agent Workflow

The agent follows a sophisticated multi-stage process:

1. **Planning Phase**
   - Validates input files exist
   - Sets up target paths and configuration
   - Initializes state management

2. **Analysis Phase**
   - Extracts PDF metadata and structure
   - Identifies tables and transaction patterns
   - Analyzes text layout and formatting

3. **Generation Phase**
   - Creates detailed prompts from analysis
   - Generates Python parser code using LLM
   - Saves parser to custom_parsers/ directory

4. **Testing Phase**
   - Imports and executes generated parser
   - Compares output with expected CSV
   - Provides detailed error diagnostics

5. **Self-Correction Phase** (if needed)
   - Analyzes test failures and error patterns
   - Generates improved parser code
   - Iterates up to maximum attempts

6. **Finalization Phase**
   - Reports final success/failure status
   - Provides detailed error logs if failed

## 🔑 Configuration

### Environment Variables
Create `.env` file with:
```
GOOGLE_API_KEY=your_google_api_key_here

# Optional: Google Gemini model selection (default: gemini-2.5-flash-lite)
GOOGLE_MODEL=gemini-2.5-flash-lite

# Optional alternatives (not currently implemented)
GROQ_API_KEY=your_groq_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

### Available Google Models
- `gemini-2.5-flash-lite` (default) - Fast, cost-effective
- `gemini-1.5-flash` - Balanced performance 
- `gemini-1.5-pro` - Higher capability
- `gemini-pro` - Legacy model

### Getting API Keys
- **Google Gemini**: Visit [Google AI Studio](https://makersuite.google.com/app/apikey)
- **Groq**: Visit [Groq Cloud](https://console.groq.com/keys) (free credits available)

## 📊 Example Output

Generated parser extracts data in this format:
```
        Date                    Description  Debit Amt  Credit Amt   Balance
0  01-08-2024    Salary Credit XYZ Pvt Ltd     1935.3         NaN   6864.58
1  02-08-2024    Salary Credit XYZ Pvt Ltd        NaN    1652.61   8517.19
2  03-08-2024    IMPS UPI Payment Amazon     3886.08         NaN   4631.11
```

## 🚨 Troubleshooting

### Common Issues

**Parser Generation Fails**
- Check API key configuration in `.env`
- Verify PDF file exists and is readable
- Ensure expected CSV format is correct

**Tests Fail**
- Check generated parser syntax
- Verify PDF parsing libraries are installed
- Review test output for specific error details

**Import Errors**
- Run `pip install -r requirements.txt`
- Check Python version compatibility (3.8+)

### Debug Mode
Enable verbose logging:
```bash
python agent.py --target icici --verbose
```

## 🔮 Extensions

### Adding New Banks
1. Add sample PDF and expected CSV to `data/{bank_name}/`
2. Run: `python agent.py --target {bank_name}`
3. The agent will automatically generate a new parser

### Performance Optimizations
- **Parallel Processing**: Analyze multiple pages simultaneously
- **Caching**: Store analysis results for faster iterations
- **Template Matching**: Use successful parsers as templates

### Enhanced Error Recovery
- **Fallback Strategies**: Multiple parsing approaches
- **Confidence Scoring**: Validate extraction quality
- **Human-in-the-Loop**: Interactive correction for edge cases

## 📈 Evaluation Metrics

The solution targets these evaluation criteria:

- **35% Agent Autonomy**: Self-debugging loops with minimal intervention
- **25% Code Quality**: Type hints, documentation, and clean architecture
- **20% Architecture**: Robust LangGraph node design and state management
- **20% Demo Speed**: Fresh clone to working parser in ≤60 seconds

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/new-bank`)
3. Add sample data to `data/{bank_name}/`
4. Test with `python agent.py --target {bank_name}`
5. Submit pull request

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

- Built on [LangGraph](https://github.com/langchain-ai/langgraph) framework
- Uses [Google Gemini](https://deepmind.google/technologies/gemini/) for code generation
- PDF processing powered by [pdfplumber](https://github.com/jsvine/pdfplumber)

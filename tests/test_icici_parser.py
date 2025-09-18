import pytest
import pandas as pd
from pathlib import Path

def test_icici_parser():
    """Test the ICICI bank statement parser"""
    # Import the parser
    try:
        from custom_parsers.icici_parser import parse
    except ImportError as e:
        pytest.fail(f"Could not import icici_parser: {e}")
    
    # Paths
    pdf_path = "data/icici/icici sample.pdf"
    csv_path = "data/icici/result.csv"
    
    # Check if files exist
    assert Path(pdf_path).exists(), f"PDF file not found: {pdf_path}"
    assert Path(csv_path).exists(), f"CSV file not found: {csv_path}"
    
    # Load expected data
    expected_df = pd.read_csv(csv_path)
    
    # Run parser
    try:
        actual_df = parse(pdf_path)
    except Exception as e:
        pytest.fail(f"Parser execution failed: {e}")
    
    # Validate return type
    assert isinstance(actual_df, pd.DataFrame), "Parser must return a pandas DataFrame"
    
    # Validate columns
    expected_columns = list(expected_df.columns)
    actual_columns = list(actual_df.columns)
    assert actual_columns == expected_columns, f"Column mismatch. Expected: {expected_columns}, Got: {actual_columns}"
    
    # Validate data
    pd.testing.assert_frame_equal(actual_df, expected_df, check_dtype=False)

def test_icici_parser_output_structure():
    """Test that the parser output has correct structure"""
    from custom_parsers.icici_parser import parse
    
    pdf_path = "data/icici/icici sample.pdf"
    result_df = parse(pdf_path)
    
    # Check required columns exist
    required_columns = ['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance']
    for col in required_columns:
        assert col in result_df.columns, f"Missing required column: {col}"
    
    # Check that we have data
    assert len(result_df) > 0, "Parser returned empty DataFrame"
    
    # Check data types are reasonable
    assert result_df['Date'].dtype == object, "Date column should be string/object"
    assert result_df['Description'].dtype == object, "Description column should be string/object"

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
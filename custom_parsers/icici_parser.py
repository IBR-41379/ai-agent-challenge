import pdfplumber
import pandas as pd
import numpy as np

def parse(pdf_path: str) -> pd.DataFrame:
    """
    Parses an ICICI bank statement PDF to extract transaction data.

    Args:
        pdf_path: The file path to the bank statement PDF.

    Returns:
        A pandas DataFrame containing transaction data with columns:
        ['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance'].
        Missing values are represented as np.nan.
    """
    all_transactions = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue

                    # Heuristic to identify transaction tables based on headers
                    # Assuming the first row is the header
                    if len(table) > 1:
                        headers = [str(h).strip() if h else '' for h in table[0]]
                        if all(h in ['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance'] for h in headers):
                            # Process rows, skipping the header row
                            for row in table[1:]:
                                if len(row) == len(headers):
                                    transaction_data = {}
                                    for i, header in enumerate(headers):
                                        value = str(row[i]).strip() if row[i] else ''
                                        transaction_data[header] = value
                                    all_transactions.append(transaction_data)
                                    if len(all_transactions) >= 100: # Limit to 100 rows as per requirement
                                        break
                            if len(all_transactions) >= 100:
                                break
                if len(all_transactions) >= 100:
                    break

    except FileNotFoundError:
        print(f"Error: The file '{pdf_path}' was not found.")
        return pd.DataFrame(columns=['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance'])
    except Exception as e:
        print(f"An error occurred during PDF parsing: {e}")
        return pd.DataFrame(columns=['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance'])

    if not all_transactions:
        return pd.DataFrame(columns=['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance'])

    df = pd.DataFrame(all_transactions)

    # Ensure all required columns exist, fill with empty strings if not
    required_columns = ['Date', 'Description', 'Debit Amt', 'Credit Amt', 'Balance']
    for col in required_columns:
        if col not in df.columns:
            df[col] = ''

    # Select and reorder columns
    df = df[required_columns]

    # Clean and normalize data
    # Date is kept as string DD-MM-YYYY
    df['Date'] = df['Date'].apply(lambda x: x if len(x) == 10 and x[2] == '-' and x[5] == '-' else '')

    # Numeric conversions
    df['Debit Amt'] = pd.to_numeric(df['Debit Amt'].str.replace(',', ''), errors='coerce')
    df['Credit Amt'] = pd.to_numeric(df['Credit Amt'].str.replace(',', ''), errors='coerce')
    df['Balance'] = pd.to_numeric(df['Balance'].str.replace(',', ''), errors='coerce')

    # Handle missing values for numeric columns by ensuring they are np.nan
    df['Debit Amt'] = df['Debit Amt'].replace('', np.nan)
    df['Credit Amt'] = df['Credit Amt'].replace('', np.nan)
    df['Balance'] = df['Balance'].replace('', np.nan)

    # Fill missing Description with empty string
    df['Description'] = df['Description'].fillna('')

    # Ensure we have exactly 100 rows, padding with NaN if necessary
    if len(df) < 100:
        padding_rows = 100 - len(df)
        padding_df = pd.DataFrame({
            'Date': [''] * padding_rows,
            'Description': [''] * padding_rows,
            'Debit Amt': [np.nan] * padding_rows,
            'Credit Amt': [np.nan] * padding_rows,
            'Balance': [np.nan] * padding_rows
        })
        df = pd.concat([df, padding_df], ignore_index=True)

    # Truncate to 100 rows if more than 100 were somehow collected
    df = df.head(100)

    # Final check for column types and NaN representation
    df['Debit Amt'] = df['Debit Amt'].astype(float)
    df['Credit Amt'] = df['Credit Amt'].astype(float)
    df['Balance'] = df['Balance'].astype(float)

    return df
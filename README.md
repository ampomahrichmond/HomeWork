# SQL Converter Web App for Collibra

A simple, elegant Python-based web application that converts SQL statements to Collibra format by prepending table references with @ symbol.

## Features

- **TD Green Theme**: Professional TD Bank green color scheme
- **Manual SQL Input**: Text box for typing or pasting SQL statements
- **Excel File Upload**: Upload Excel files containing SQL queries
- **Database Connections**: Connect to SQLite, PostgreSQL, and Oracle databases
- **Multiple Download Formats**: Download results as Excel or JSON
- **Collibra Integration**: Framework for connecting to Collibra (REST API integration)
- **Side-by-Side Comparison**: View original and converted SQL statements
- **Real-time Preview**: See conversion results immediately

## Installation & Setup

1. **Clone or download the files**
   ```bash
   # Download the sql_converter_app.py and requirements.txt files
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   streamlit run sql_converter_app.py
   ```

4. **Access the app**
   - Open your browser and go to `http://localhost:8501`

## Usage

### Manual SQL Input
1. Select "Manual SQL Input" option
2. Enter your SQL statement in the text area
3. Click "Convert SQL" button
4. View the converted SQL with @ symbols added before table names

### Excel File Upload
1. Select "Excel File Upload" option
2. Upload an Excel file with a column named "SQL"
3. Click "Process Excel File" button
4. Download the results as Excel or JSON

### Database Connections
1. Use the sidebar to connect to your database
2. Choose from SQLite, PostgreSQL, or Oracle
3. Enter connection details and click connect
4. Execute queries directly from the app

### Download Options
- **Excel Format**: Download as .xlsx file with Original_SQL and Collibra_SQL columns
- **JSON Format**: Download as .json file with structured data

## SQL Conversion Logic

The app converts SQL by adding @ before table names that follow these keywords:
- FROM
- JOIN (all types: INNER, LEFT, RIGHT, FULL, CROSS)
- OUTER JOIN variations

**Example:**
```sql
-- Original
SELECT * FROM DB2.ADR_XY3 
INNER JOIN schema.table2 ON condition

-- Converted
SELECT * FROM @DB2.ADR_XY3 
INNER JOIN @schema.table2 ON condition
```

## File Structure

```
sql_converter_app.py    # Main application file (single file solution)
requirements.txt        # Python dependencies
README.md              # This documentation
sample_data.xlsx       # Sample Excel file for testing
```

## Sample Excel File Format

Create an Excel file with the following structure:

| SQL |
|-----|
| SELECT * FROM table1 |
| SELECT col1 FROM schema.table2 WHERE id = 1 |
| SELECT a.*, b.name FROM table_a a JOIN table_b b ON a.id = b.id |

## Dependencies

- **streamlit**: Web application framework
- **pandas**: Data manipulation and analysis
- **openpyxl**: Excel file handling
- **sqlalchemy**: Database connectivity
- **psycopg2-binary**: PostgreSQL adapter
- **cx-Oracle**: Oracle database adapter

## Database Support

### SQLite
- File-based database
- No additional setup required

### PostgreSQL
- Requires PostgreSQL server
- Connection parameters: host, port, database, username, password

### Oracle
- Requires Oracle client libraries
- Connection parameters: host, port, service_name, username, password

## Collibra Integration

The app includes a framework for Collibra integration:
- Connection form in sidebar
- Ready for REST API implementation
- View reading capabilities (to be implemented)

## Customization

The app uses a TD green theme with:
- Primary color: #00a651 (TD Green)
- Secondary color: #007a3d (Dark TD Green)
- Background gradients and professional styling

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed
   ```bash
   pip install -r requirements.txt
   ```

2. **Database Connection Issues**: 
   - Check connection parameters
   - Ensure database server is running
   - Verify network connectivity

3. **Excel File Issues**:
   - Ensure Excel file has a column named "SQL"
   - Check file format (.xlsx or .xls)

### Oracle Setup
For Oracle connections, you may need to install Oracle Instant Client:
1. Download Oracle Instant Client
2. Set environment variables (ORACLE_HOME, LD_LIBRARY_PATH)
3. Install cx_Oracle package

## License

This project is open source and available under the MIT License.

## Support

For issues or questions:
1. Check the troubleshooting section
2. Verify all dependencies are installed
3. Ensure database connections are properly configured

import dash
from dash import dcc, html, Input, Output, State
import pandas as pd
import json
import os
import re
import base64
import io
from dash import callback_context
from dash_ag_grid import AgGrid
from dash import dash_table

import logging
from dash import Dash

# Set the overall logging level to DEBUG
logging.basicConfig(level=logging.DEBUG)

# Optionally, silence the extensive 'POST /dash/_dash-update-component' messages
logging.getLogger('tds-ai').setLevel(logging.DEBUG) # set to ERROR to hide request logs


data_dir = 'data'
clients_file = os.path.join(data_dir, 'clients.csv')
sections_file = os.path.join(data_dir, 'sections.json')
transactions_file = os.path.join(data_dir, 'transactions.csv')

# PAN validation regex (case-insensitive)
PAN_REGEX = re.compile(r'^[A-Z]{5}[0-9]{4}[A-Z]$', re.IGNORECASE)

# Load static section mapping
with open(sections_file, 'r') as f:
    SECTION_MAP = json.load(f)

app = dash.Dash(__name__)
app.title = 'TDS Deduction Report Engine'

# Helper functions

def load_clients():
    if os.path.exists(clients_file):
        return pd.read_csv(clients_file)
    return pd.DataFrame(columns=['client_name', 'PAN', 'address'])

def save_clients(df):
    df.to_csv(clients_file, index=False)

def load_transactions():
    if os.path.exists(transactions_file):
        return pd.read_csv(transactions_file)
    return pd.DataFrame(columns=[
        'transaction_id', 'client_name', 'principal_amount', 'tax_code_section',
        'date_of_transaction', 'date_of_tax_deduction', 'date_of_tax_payment'
    ])

def save_transactions(df):
    df.to_csv(transactions_file, index=False)

def validate_pan(pan, existing_pans=None):
    pan = pan.upper()
    if not PAN_REGEX.match(pan):
        return False, 'Invalid PAN format.'
    if existing_pans is not None and pan in [p.upper() for p in existing_pans]:
        return False, 'Duplicate PAN.'
    return True, ''

# Layout
app.layout = html.Div([
    dcc.Tabs([
        dcc.Tab(label='Clients', children=[
            html.H3('Client Database'),
            html.Div([
                html.Label('Client Name'),
                dcc.Input(id='client-name-input', type='text', placeholder='Enter client name'),
                html.Label('PAN'),
                dcc.Input(id='client-pan-input', type='text', placeholder='Enter PAN'),
                html.Label('Address'),
                dcc.Input(id='client-address-input', type='text', placeholder='Enter address'),
                html.Button('Add Client', id='add-client-btn'),
                html.Div(id='client-add-status', style={'color': 'red', 'marginTop': '10px'}),
            ], style={'display': 'flex', 'flexDirection': 'column', 'maxWidth': '400px', 'gap': '8px'}),
            html.Hr(),
            dash_table.DataTable(
                id='clients-table',
                columns=[
                    {'name': 'Client Name', 'id': 'client_name'},
                    {'name': 'PAN', 'id': 'PAN'},
                    {'name': 'Address', 'id': 'address'}
                ],
                data=[],
                page_size=10
            ),
        ]),
        dcc.Tab(label='Transactions', children=[
            html.H3('Transaction Entry'),
            dcc.Upload(
                id='upload-transactions',
                children=html.Button('Upload Transactions CSV'),
                multiple=False
            ),
            html.Div(id='upload-transactions-error', style={'color': 'red'}),
            AgGrid(
                id='transactions-table',
                columnDefs=[
                    {'headerName': 'Transaction ID', 'field': 'transaction_id', 'editable': True},

                    {
                        'headerName': 'Client Name',
                        'field': 'client_name',
                        'editable': True,
                        'cellEditor': 'agSelectCellEditor',
                        'cellEditorParams': {
                            'values': list(load_clients()['client_name'].dropna().unique())
                        }
                    },

                    {'headerName': 'Principal Amount', 'field': 'principal_amount', 'editable': True, 'type': 'numericColumn'},

                    {
                        'headerName': 'Tax Code Section',
                        'field': 'tax_code_section',
                        'editable': True,
                        'cellEditor': 'agSelectCellEditor',
                        'cellEditorParams': {'values': list(SECTION_MAP.keys())}
                    },

                    # -----------------------
                    #   DATE COLUMNS
                    # -----------------------

                    {
                        "headerName": "Date of Transaction",
                        "field": "date_of_transaction",
                        "editable": True,
                        "cellEditor": "FlatpickrDateEditor",
                        "valueFormatter": {"function": "return params.value || '';"}
                    },
                    {
                        "headerName": "Date of Tax Deduction",
                        "field": "date_of_tax_deduction",
                        "editable": True,
                        "cellEditor": "FlatpickrDateEditor",
                        "valueFormatter": {"function": "return params.value || '';"}
                    },
                    {
                        "headerName": "Date of Tax Payment",
                        "field": "date_of_tax_payment",
                        "editable": True,
                        "cellEditor": "FlatpickrDateEditor",
                        "valueFormatter": {"function": "return params.value || '';"}
                    }

                ],

                rowData=[],

                defaultColDef={'flex': 1, 'minWidth': 120, 'resizable': True},

                dashGridOptions={
                    'rowSelection': 'multiple',
                    'stopEditingWhenCellsLoseFocus': True
                },

                style={'height': '400px', 'width': '100%'},
            ),
            html.Button('Add Row', id='add-transaction-row'),
            html.Button('Save Transactions', id='save-transactions'),
            html.Div(id='transactions-save-status', style={'color': 'green'}),
        ]),
        dcc.Tab(label='Reports', children=[
            html.H3('TDS Reports'),
            dcc.DatePickerRange(
                id='report-date-range',
                display_format='YYYY-MM-DD',
            ),
            dcc.Dropdown(
                id='report-period',
                options=[
                    {'label': 'Monthly', 'value': 'monthly'},
                    {'label': 'Quarterly', 'value': 'quarterly'},
                    {'label': 'Yearly', 'value': 'yearly'}
                ],
                placeholder='Select preset period',
            ),
            html.Button('Export Transactions CSV', id='export-transactions'),
            html.A('Download CSV', id='download-link', href='', target='_blank', style={'display': 'none'}),
            dash_table.DataTable(
                id='report-table',
                page_size=20
            ),
        ]),
    ])
])

# --- CLIENTS TAB CALLBACKS ---
@app.callback(
    Output('clients-table', 'data'),
    Output('client-add-status', 'children'),
    Input('clients-table', 'data_timestamp'),
    Input('add-client-btn', 'n_clicks'),
    State('client-name-input', 'value'),
    State('client-pan-input', 'value'),
    State('client-address-input', 'value'),
    State('clients-table', 'data'),
    prevent_initial_call=False
)
def manage_clients(ts, add_clicks, name, pan, address, current_data):
    ctx = callback_context
    df = load_clients()
    status_message = ''

    if ctx.triggered:
        trigger = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger == 'add-client-btn':
            errors = []
            name = str(name or '').strip()
            pan = str(pan or '').upper().strip()
            address = str(address or '').strip()
            if not name or not pan or not address:
                errors.append('All fields are required.')
            valid, msg = validate_pan(pan, df['PAN'].str.upper() if not df.empty else [])
            if not valid:
                errors.append(msg)
            if not errors:
                new_row = {'client_name': name, 'PAN': pan, 'address': address}
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                save_clients(df)
                status_message = 'Client added successfully.'
            else:
                status_message = '\n'.join(errors)

    return df.to_dict('records'), status_message

# --- TRANSACTIONS TAB CALLBACKS ---
@app.callback(
    Output('transactions-table', 'rowData'),
    Output('upload-transactions-error', 'children'),
    Input('upload-transactions', 'contents'),
    Input('add-transaction-row', 'n_clicks'),
    State('upload-transactions', 'filename'),
    State('transactions-table', 'rowData'),
    prevent_initial_call=True
)
def update_transactions_table(upload_contents, add_row_clicks, upload_filename, current_rowData):
    ctx = callback_context
    error_msg = ''
    df = load_transactions()
    if ctx.triggered:
        trigger = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger == 'upload-transactions' and upload_contents:
            content_type, content_string = upload_contents.split(',')
            decoded = base64.b64decode(content_string)
            try:
                df_new = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
            except Exception as e:
                error_msg = f'Error reading file: {e}'
                return current_rowData, error_msg
            required = {'transaction_id', 'client_name', 'principal_amount', 'tax_code_section', 'date_of_transaction', 'date_of_tax_deduction', 'date_of_tax_payment'}
            if not required.issubset(df_new.columns):
                error_msg = 'Missing required columns.'
                return current_rowData, error_msg
            df_existing = load_transactions()
            df_valid = df_new[~df_new['transaction_id'].isin(df_existing['transaction_id'])]
            df_all = pd.concat([df_existing, df_valid], ignore_index=True)
            save_transactions(df_all)
            return df_all.to_dict('records'), error_msg
        elif trigger == 'add-transaction-row':
            if current_rowData is None:
                current_rowData = []
            current_rowData.append({
                'transaction_id': '',
                'client_name': '',
                'principal_amount': '',
                'tax_code_section': '',
                'date_of_transaction': '',
                'date_of_tax_deduction': '',
                'date_of_tax_payment': ''
            })
            return current_rowData, error_msg
    return current_rowData, error_msg

@app.callback(
    Output('report-table', 'data'),
    Output('report-table', 'columns'),
    Input('report-date-range', 'start_date'),
    Input('report-date-range', 'end_date'),
    Input('report-period', 'value'),
    prevent_initial_call=True
)
def update_report_table(start_date, end_date, period):
    df = load_transactions()
    # Filter by date range
    if start_date and end_date:
        df = df[(df['date_of_transaction'] >= start_date) & (df['date_of_transaction'] <= end_date)]
    # Add TDS and interest calculations
    def calc_tds(row):
        rate = SECTION_MAP.get(str(row['tax_code_section']).strip(), 0)
        return float(row['principal_amount']) * rate
    def calc_interest(row):
        from datetime import datetime
        def to_date(s):
            try:
                return datetime.strptime(str(s)[:10], '%Y-%m-%d')
            except:
                return None
        dt_trans = to_date(row['date_of_transaction'])
        dt_deduct = to_date(row['date_of_tax_deduction'])
        dt_pay = to_date(row['date_of_tax_payment'])
        if not (dt_trans and dt_deduct and dt_pay):
            return 0.0
        principal = float(row['principal_amount'])
        section = str(row['tax_code_section']).strip()
        tds = principal * SECTION_MAP.get(section, 0)
        # Deadline: 7th of next month after transaction
        deadline_month = dt_trans.month + 1 if dt_trans.month < 12 else 1
        deadline_year = dt_trans.year if dt_trans.month < 12 else dt_trans.year + 1
        deadline_day = 7
        deadline = datetime(deadline_year, deadline_month, deadline_day)
        if dt_pay <= deadline:
            return 0.0
        # Special case: year-end deduction
        is_year_end = dt_deduct.month == 3 and dt_deduct.day == 31
        if is_year_end:
            dt_deduct = datetime(dt_deduct.year + 1, 4, 1)
            # If paid before Apr 30, April interest is waived
            if dt_pay <= datetime(dt_deduct.year, 4, 30):
                months_1 = 2  # Feb, Mar at 1%
                interest = tds * 0.01 * months_1
                return round(interest, 2)
            else:
                # Feb, Mar at 1%, Apr+ at 1.5%
                months_1 = 2
                months_15 = (dt_pay.year - dt_deduct.year) * 12 + (dt_pay.month - 4) + 1
                interest = tds * 0.01 * months_1 + tds * 0.015 * months_15
                return round(interest, 2)
        # General case
        # Months at 1%: from transaction month to month before deduction
        months_1 = (dt_deduct.year - dt_trans.year) * 12 + (dt_deduct.month - dt_trans.month)
        if months_1 < 0:
            months_1 = 0
        # Months at 1.5%: from deduction month to payment month
        months_15 = (dt_pay.year - dt_deduct.year) * 12 + (dt_pay.month - dt_deduct.month) + 1
        if months_15 < 0:
            months_15 = 0
        interest = tds * 0.01 * months_1 + tds * 0.015 * months_15
        return round(interest, 2)
    df['TDS'] = df.apply(calc_tds, axis=1)
    df['Interest'] = df.apply(calc_interest, axis=1)
    df['Total Payment'] = df['TDS'] + df['Interest']
    columns = [{'name': col, 'id': col} for col in df.columns]
    return df.to_dict('records'), columns

@app.callback(
    Output('download-link', 'href'),
    Output('download-link', 'style'),
    Input('export-transactions', 'n_clicks'),
    prevent_initial_call=True
)
def export_transactions(n):
    df = load_transactions()
    csv_string = df.to_csv(index=False, encoding='utf-8')
    href = 'data:text/csv;charset=utf-8,' + base64.b64encode(csv_string.encode()).decode()
    return href, {'display': 'block'}

# --- TRANSACTIONS TAB CALLBACKS ---
@app.callback(
    Output('transactions-save-status', 'children'),
    Input('save-transactions', 'n_clicks'),
    State('transactions-table', 'rowData'),
    prevent_initial_call=True
)
def save_transactions_callback(n_clicks, rowData):
    if rowData is None:
        return 'No data to save.'
    try:
        df = pd.DataFrame(rowData)
        save_transactions(df)
        return 'Transactions saved successfully.'
    except Exception as e:
        return f'Error saving transactions: {e}'

if __name__ == '__main__':
    app.run(debug=True)

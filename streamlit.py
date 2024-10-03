import io

import boto3
import fitz
import pandas as pd

import streamlit as st


def get_text(result, blocks_map):
    text = ""
    if "Relationships" in result:
        for relationship in result["Relationships"]:
            if relationship["Type"] == "CHILD":
                for child_id in relationship["Ids"]:
                    word = blocks_map[child_id]
                    if word["BlockType"] == "WORD":
                        if (
                            "," in word["Text"]
                            and word["Text"].replace(",", "").isnumeric()
                        ):
                            text += '"' + word["Text"] + '"' + " "
                        else:
                            text += word["Text"] + " "
                    if word["BlockType"] == "SELECTION_ELEMENT":
                        if word["SelectionStatus"] == "SELECTED":
                            text += "X "
    return text


def get_rows__map(table_result, blocks_map):
    rows = {}
    scores = []
    for relationship in table_result["Relationships"]:
        if relationship["Type"] == "CHILD":
            for child_id in relationship["Ids"]:
                cell = blocks_map[child_id]
                if cell["BlockType"] == "CELL":
                    row_index = cell["RowIndex"]
                    col_index = cell["ColumnIndex"]
                    if row_index not in rows:
                        # create new row
                        rows[row_index] = {}

                    # get confidence score
                    scores.append(str(cell["Confidence"]))

                    # get the text value
                    rows[row_index][col_index] = get_text(cell, blocks_map)
    return rows, scores


# Create a Textract client
textract = boto3.client("textract", region_name="ap-southeast-2")

# Create a Streamlit file uploader for the user to upload PDFs
uploaded_files = st.file_uploader(
    "Upload a PDF:", type=["pdf"], accept_multiple_files=True
)

transactions = pd.DataFrame(
    columns=["Date", "Transaction", "Credit", "Debit", "Balance"]
)

junk = []

# Create a Streamlit button to trigger the analysis
if uploaded_files and st.button("Convert to CSV"):
    # Split the uploaded PDF by page
    pages = []
    progress_bar = st.progress(0, text="Analyzing PDFs...")
    # Open the uploaded file with PyMuPDF
    for uploaded_file_index, uploaded_file in enumerate(uploaded_files):
        with fitz.open(stream=uploaded_file.getvalue(), filetype="pdf") as doc:
            # Split the PDF into individual pages
            for page_index in range(doc.page_count):
                page = doc.load_page(page_index)
                # Save the page to memory
                page_bytes = io.BytesIO()
                # Save the page to memory
                page_bytes.write(page.get_pixmap().tobytes())
                page_bytes.seek(0)
                # Encode the page bytes as base64
                response = textract.analyze_document(
                    Document={"Bytes": page_bytes.read()}, FeatureTypes=["TABLES"]
                )
                progress_bar.progress(
                    (uploaded_file_index) / len(uploaded_files),
                    text=f"Analyzing {uploaded_file.name}: page {page_index+1} of {doc.page_count}",
                )
                # Use the response to construct a Pandas DataFrame
                blocks = response["Blocks"]
                blocks_map = {}
                table_blocks = []
                for block in blocks:
                    blocks_map[block["Id"]] = block
                    if block["BlockType"] == "TABLE":
                        table_blocks.append(block)

                if len(table_blocks) < 1:
                    continue

                for index, table in enumerate(table_blocks):
                    rows, scores = get_rows__map(table, blocks_map)
                    headers = rows.get(1, {})
                    if "Date" not in headers.get(1, ""):
                        continue
                    del rows[1]  # delete the headers
                    try:
                        df = pd.DataFrame.from_dict(rows, orient="index")
                        df.columns = [
                            "Date",
                            "Transaction",
                            "Credit",
                            "Debit",
                            "Balance",
                        ]
                        year = uploaded_file.name[10:14]
                        df["Date"] = df["Date"].astype(str) + " " + year

                        # Censoring
                        #df["Transaction"] = "XXXX"
                        #df["Credit"] = "$0.00"
                        #df["Debit"] = "$0.00"
                        #df["Balance"] = "$0.00"
                        transactions = pd.concat([transactions, df])
                    except:
                        # { 1: Date, 2: Transaction
                        # }
                        for row in rows.values():
                            columns = len(headers.keys())
                            junk_row = [row.get(i) for i in range(columns)]
                            junk.append(junk_row)

    progress_bar.progress(
        100,
        text="Analysis Complete",
    )
    st.table(transactions)

    st.download_button(
        label="Download transactions as CSV",
        data=transactions.to_csv(index=False),
        file_name="transactions.csv",
        mime="text/csv",
    )
    st.warning("These transactions could not be recognised, please add them manually")
    st.dataframe(junk)

import fitz  # PyMuPDF library for PDF handling
import re  # Regular expression module for text processing
import os  # For checking file existence
import time  # For measuring execution time
import pickle  # For saving and loading preprocessed data
from flask import Flask, render_template, request, jsonify, send_file
from concurrent.futures import ProcessPoolExecutor, as_completed

app = Flask(__name__)

# Global variable for PDF file path
PDF_FILE_PATH = 'Resources/physText.pdf'
INDEX_FILE_PATH = 'Resources/index.pkl'

# Function to extract text and sentences from a page
def extract_sentences(page_num, text):
    sentences = re.split(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s', text)
    return [{'Page Number': page_num + 1, 'Sentence': sentence} for sentence in sentences]

# Pre-process the PDF to create an index and sort it by page number
def preprocess_pdf(pdf_file):
    index = []
    try:
        pdf_document = fitz.open(pdf_file)
        with ProcessPoolExecutor() as executor:
            futures = [executor.submit(extract_sentences, page_num, pdf_document.load_page(page_num).get_text("text")) for page_num in range(len(pdf_document))]
            for future in as_completed(futures):
                index.extend(future.result())
        # Sort the index by page number
        index.sort(key=lambda x: x['Page Number'])
    except Exception as e:
        print(f"An error occurred during preprocessing: {e}")
    return index

# Save the preprocessed index to a file
def save_index_to_file(index, filename):
    with open(filename, 'wb') as file:
        pickle.dump(index, file)

# Load the preprocessed index from a file
def load_index_from_file(filename):
    with open(filename, 'rb') as file:
        return pickle.load(file)

# Search for keywords in the preprocessed index
def search_keywords_in_index(index, keywords):
    all_data = []
    for entry in index:
        for keyword in keywords:
            if keyword.lower() in entry['Sentence'].lower():
                all_data.append({'Keyword': keyword, 'Page Number': entry['Page Number'], 'Sentence': entry['Sentence']})
    return all_data

# Main function to search keywords in the PDF
def search_keywords_in_pdf(pdf_file, keywords):
    if not os.path.isfile(pdf_file):
        print("No such file:", os.path.basename(pdf_file))
        return [], 0.0
    
    start_time = time.time()

    if os.path.isfile(INDEX_FILE_PATH):
        index = load_index_from_file(INDEX_FILE_PATH)
    else:
        index = preprocess_pdf(pdf_file)
        save_index_to_file(index, INDEX_FILE_PATH)
    
    found_data = search_keywords_in_index(index, keywords)
    
    end_time = time.time()
    duration = end_time - start_time
    
    return found_data, duration

# Initialization function to preprocess the PDF and save the index
def initialize_index(pdf_file, index_file):
    print("Initializing index...")
    if not os.path.isfile(index_file):
        index = preprocess_pdf(pdf_file)
        save_index_to_file(index, index_file)
        print("PDF preprocessing complete and index saved.")
    else:
        print("Index file already exists. Skipping preprocessing.")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    keywords = data['keywords']
    found_data, duration = search_keywords_in_pdf(PDF_FILE_PATH, keywords)
    response = {
        'results': found_data,
        'duration': duration
    }
    return jsonify(response)

@app.route('/view_pdf')
def view_pdf():
    page_number = request.args.get('page')
    return send_file(PDF_FILE_PATH)

if __name__ == '__main__':
    # Initialize the index
    initialize_index(PDF_FILE_PATH, INDEX_FILE_PATH)
    
    # Start the Flask application
    app.run(debug=True)
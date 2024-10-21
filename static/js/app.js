var socket = io();  // Connects to the server using Socket.IO

// Listen for progress updates from the server
socket.on('progress', function (data) {
    const progress = data.progress;
    document.getElementById('progress-bar').value = progress;
    document.getElementById('progress-text').textContent = `${progress.toFixed(2)}%`;
});

// Listen for updates to the PDF titles dropdown
socket.on('update_pdf_titles', function (pdfTitles) {
    updatePdfTitleDropdown(pdfTitles);
    updateRemoveFileDropdown(pdfTitles);
});

// Update PDF Titles Dropdown
function updatePdfTitleDropdown(pdfTitles) {
    const pdfTitleDropdown = document.getElementById('pdf-title-dropdown');
    pdfTitleDropdown.innerHTML = '<option value="">Select PDF Title</option>'; // Clear existing options
    pdfTitles.forEach(title => {
        const option = document.createElement('option');
        option.value = title;
        option.textContent = title;
        pdfTitleDropdown.appendChild(option);
    });
}

// Update Remove File Dropdown
function updateRemoveFileDropdown(pdfTitles) {
    const removeFileDropdown = document.getElementById('remove-file-dropdown');
    removeFileDropdown.innerHTML = '<option value="">Select PDF Title</option>'; // Clear existing options
    pdfTitles.forEach(title => {
        const option = document.createElement('option');
        option.value = title;
        option.textContent = title;
        removeFileDropdown.appendChild(option);
    });
}

// Handle Upload Form Submission
document.getElementById('upload-form').addEventListener('submit', function (event) {
    event.preventDefault(); // Prevent default form submission
    const formData = new FormData(event.target); // Collect form data
    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/upload', true);

    // Update progress bar during upload
    xhr.upload.onprogress = function (event) {
        if (event.lengthComputable) {
            const percentComplete = (event.loaded / event.total) * 100;
            document.getElementById('progress-bar').value = percentComplete;
            document.getElementById('progress-text').textContent = `${percentComplete.toFixed(2)}%`;
            document.getElementById('loading-container').style.display = 'block';
        }
    };

    // Handle response after upload
    xhr.onload = function () {
        if (xhr.status === 200) {
            hideUploadModal();
            resetProgressBar();
            alert('File uploaded successfully!');
        } else if (xhr.status === 400) {
            const response = JSON.parse(xhr.responseText);
            alert(response.error || 'Failed to upload file.');
        } else {
            alert('Failed to upload file.');
        }
    };

    // Send the form data
    xhr.send(formData);
});

// Function to reset the progress bar
function resetProgressBar() {
    document.getElementById('progress-bar').value = 0;
    document.getElementById('progress-text').textContent = '0%';
    document.getElementById('loading-container').style.display = 'none';
}

// Keyword search enter key
document.getElementById('keywords').addEventListener('keypress', function(event) {
    if (event.key === 'Enter') { 
        searchKeywords();
    }
});

// Function to initiate search based on keywords
function searchKeywords() {
    const keywordsInput = document.getElementById("keywords").value;
    const keywords = keywordsInput.split(",").map(keyword => keyword.trim()).filter(k => k); // Remove empty strings
    const pdfTitle = document.getElementById("pdf-title-dropdown").value;

    // Validate that at least one keyword is entered
    if (keywords.length === 0) {
        alert('Please enter at least one keyword to search.');
        return;
    }

    // Send search request to the server
    fetch('/search', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ keywords, pdf_title: pdfTitle }),
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert(data.error);
            return;
        }
        displaySearchInfo(data);
        displayResults(data.results.tkData, data.results.pdfData, keywords);
    })
    .catch(error => console.error('Error:', error));
}

// Function to display search information like duration and number of results
function displaySearchInfo(data) {
    const searchInfoDiv = document.getElementById("search-info");
    searchInfoDiv.innerHTML = `<b>Search Duration:</b> ${data.duration.toFixed(3)} seconds <br><b>Results Found:</b> ${data.num_results}`;

    // Reveal the results sections
    document.getElementById("traible-knowledge-heading").classList.remove("hidden");
    document.getElementById("pdf-results-heading").classList.remove("hidden");
}

// Function to navigate to a specific page in the PDF
function intraNavToPdf(pageNumber, title) {
    const url = `/view_pdf?title=${encodeURIComponent(title)}#page=${pageNumber}`;
    window.location.href = url;
}

// Function to open the forum in a new window
function openForum() {
    window.open("/forum", "Forum", "width=600,height=600");
}

// Event listener to close the modal when clicking outside of it
window.onclick = function(event) {
    const modal = document.getElementById('upload-modal');
    if (event.target == modal) {
        hideUploadModal();
    }
}

// Function to show the upload modal
function showUploadModal(mandatory = false) {
    const modal = document.getElementById('upload-modal');
    const closeBtn = modal.querySelector('.close');
    modal.style.display = 'block';
    
    if (mandatory) {
        closeBtn.style.display = 'none';
        modal.addEventListener('click', preventClose);
    } else {
        closeBtn.style.display = 'block';
        modal.onclick = function(event) {
            if (event.target === modal) {
                hideUploadModal();
            }
        };
    }
}

// Function to hide the upload modal
function hideUploadModal() {
    const modal = document.getElementById('upload-modal');
    modal.style.display = 'none';
    modal.removeEventListener('click', preventClose);
}

// Function to ensure a file is selected before uploading
function checkFileUploaded() {
    const fileInput = document.getElementById('file-input');
    if (!fileInput.value) {
        alert('You must upload a file before proceeding.');
        return false;
    }
    return true;
}

// Function to prevent closing the modal when mandatory
function preventClose(event) {
    if (event.target === document.getElementById('upload-modal')) {
        event.preventDefault();
        event.stopPropagation();
    }
}

// Initialize event listeners once the DOM is fully loaded
document.addEventListener('DOMContentLoaded', function() {
    // Show upload modal if required on initial load
    if (initialUploadRequired) {
        showUploadModal(true);
    }

    // Show close button when a file is selected
    const fileInput = document.getElementById('file-input');
    fileInput.addEventListener('change', function() {
        if (fileInput.value) {
            document.querySelector('.modal .close').style.display = 'block';
        }
    });

    // Trigger search when a different PDF title is selected
    const pdfTitleDropdown = document.getElementById('pdf-title-dropdown');
    pdfTitleDropdown.addEventListener('change', function() {
        searchKeywords();
    });
});

// Function to display search results in the UI
function displayResults(tkResults, pdfResults, keywords) {
    const container = document.getElementById("container");
    const tkResultsDiv = document.getElementById("tk-results");
    const pdfResultsDiv = document.getElementById("pdf-results");
    const traibleKnowledgeHeading = document.getElementById("traible-knowledge-heading");
    const pdfResultsHeading = document.getElementById("pdf-results-heading");

    container.classList.remove("hidden");

    // Clear previous results
    tkResultsDiv.innerHTML = "";
    pdfResultsDiv.innerHTML = "";

    let tkResultsFound = false;
    let pdfResultsFound = false;

    // Display Traible Knowledge Forum Results
    if (tkResults.length > 0) {
        traibleKnowledgeHeading.classList.remove("hidden");
        keywords.forEach(keyword => {
            const keywordDiv = document.createElement("div");
            const keywordHeading = document.createElement("h3");
            const keywordResultsDiv = document.createElement("div");
            keywordResultsDiv.classList.add("keyword-results");

            // Filter results for the current keyword
            const keywordResults = tkResults.filter(result => {
                return result['Problem Description'].toLowerCase().includes(keyword.toLowerCase()) || 
                       result['Solution'].toLowerCase().includes(keyword.toLowerCase());
            });

            if (keywordResults.length > 0) {
                tkResultsFound = true;
                keywordHeading.innerText = `Results for "${keyword}"`;
                keywordHeading.classList.add("keyword-heading");
                
                // Populate results
                keywordResults.forEach(result => {
                    const resultDiv = document.createElement("div");
                    resultDiv.classList.add("result-item");
                    resultDiv.innerHTML = `
                        <b>Submitted by:</b> ${result.Name}<br>
                        <b>Problem Description:</b> ${result['Problem Description']}<br>
                        <b>Solution:</b> ${result.Solution}<br>
                        <b>Chapter:</b> ${result.Chapter}<br>
                    `;
                    keywordResultsDiv.appendChild(resultDiv);
                });

                keywordDiv.appendChild(keywordHeading);
                keywordDiv.appendChild(keywordResultsDiv);
                tkResultsDiv.appendChild(keywordDiv);
            }
        });

        // If no results found for single keyword
        if (!tkResultsFound && keywords.length === 1) {
            tkResultsDiv.innerHTML = `No results found for "${keywords[0]}".`;
        }
    } else {
        tkResultsDiv.innerHTML = `No results found for "${keywords.join(', ')}".`;
    }

    // Display PDF Search Results
    if (pdfResults.length > 0) {
        pdfResultsHeading.classList.remove("hidden");
        document.getElementById("pdf-title-dropdown").classList.remove("hidden");
        keywords.forEach(keyword => {
            const keywordDiv = document.createElement("div");
            const keywordHeading = document.createElement("h3");
            const keywordResultsDiv = document.createElement("div");
            keywordResultsDiv.classList.add("keyword-results");

            // Filter PDF results for the current keyword
            const keywordResults = pdfResults.filter(result => {
                return result.Keyword && result.Keyword.toLowerCase().includes(keyword.toLowerCase());
            });

            if (keywordResults.length > 0) {
                pdfResultsFound = true;
                keywordHeading.innerText = `Results for "${keyword}"`;
                keywordHeading.classList.add("keyword-heading");
                
                // Populate PDF results with clickable links
                keywordResults.forEach(result => {
                    const link = document.createElement("a");
                    link.innerHTML = `
                        ${result.Sentence}<br>
                        <b>PDF Title:</b> ${result.Title}<br>
                        <b>Page Number:</b> ${result['Page Number']}<br>
                    `;
                    link.href = "#";
                    link.onclick = () => intraNavToPdf(result['Page Number'], result.Title);
                    keywordResultsDiv.appendChild(link);
                    keywordResultsDiv.appendChild(document.createElement("br"));
                });

                keywordDiv.appendChild(keywordHeading);
                keywordDiv.appendChild(keywordResultsDiv);
                pdfResultsDiv.appendChild(keywordDiv);
            }
        });

        // If no results found for single keyword
        if (!pdfResultsFound && keywords.length === 1) {
            pdfResultsDiv.innerHTML = `No results found for "${keywords[0]}".`;
        }
    } else {
        pdfResultsDiv.innerHTML = `No results found for "${keywords.join(', ')}".`;
    }
}

// Function to confirm and remove a selected PDF file
function confirmAndRemoveFile(event) {
    event.preventDefault();
    const fileDropdown = document.getElementById('remove-file-dropdown');
    const selectedFile = fileDropdown.value;

    // Ensure a file is selected
    if (!selectedFile) {
        alert('Please select a file to remove.');
        return false;
    }

    // Confirm removal with the user
    const confirmation = confirm(`Are you sure you want to remove the file: "${selectedFile}"?`);
    if (confirmation) {
        // Send a POST request to remove the file
        fetch('/remove_file', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 'file_name': selectedFile }),
        })
        .then(response => response.json())
        .then(data => {
            if (data.message) {
                alert(data.message);
                // Trigger an update to PDF titles
                socket.emit('update_pdf_titles');
            } else if (data.error) {
                alert('Error: ' + data.error);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred while removing the file.');
        });
    }
}

// AI Chat functionality
function sendMessage() {
    const message = document.getElementById('user-input').value;
    if (message.trim() !== '') {
        socket.emit('send_message', {message: message});  // Emit message to server
        document.getElementById('chat-messages').innerHTML += '<p class="user-message"><strong>You:</strong> ' + message + '</p>';  // Append user message
        document.getElementById('user-input').value = '';  // Clear input field
    }
}

let isNewResponse = true; // Tracks if a new response should start

// Listen for each word being sent back from the server
socket.on('receive_message', function(data) {
    let lastMessage = $('#chat-messages').find('.ai-response:last');

    // If it's a new response or there are no previous AI messages, create a new paragraph
    if (isNewResponse || lastMessage.length === 0) {
        $('#chat-messages').append('<p class="ai-response"><strong>AI:</strong> <span class="response-text"></span></p>');
        lastMessage = $('#chat-messages').find('.ai-response:last .response-text');
        isNewResponse = false;  // Mark that we're continuing this response
    } else {
        lastMessage = $('#chat-messages').find('.ai-response:last .response-text');
    }

    // Append the new word to the current AI response
    lastMessage.append(data.message + ' ');
});

// Listen for 'Enter' key in the user input field 
document.getElementById('user-input').addEventListener('keypress', function(event) {
    if (event.key === 'Enter') {  // Send message if 'Enter' key is pressed
        sendMessage();
    }
});

// After the user sends a message, reset for a new AI response
function sendMessage() {
    var message = $('#user-input').val();
    if (message.trim() !== '') {
        socket.emit('send_message', {message: message});
        $('#chat-messages').append('<p class="user-message"><strong>You:</strong> ' + message + '</p>');
        $('#user-input').val('');

        // After user sends a message, set flag to start a new AI response
        isNewResponse = true;
    }
}
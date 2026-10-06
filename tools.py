TOOL_ICONS = {
    "list_files": "📁",
    "read_file": "📖",
    "edit_file": "✏️",
    "delete_file": "🗑️",
    "save_memory": "🧠",
}


tools = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "Lists files and directories in the specified directory. Returns plain names in 'files' and items with name, type, and icon in 'entries'. Display each entry as a Markdown bullet with its icon followed by its exact name in plain text, without surrounding quotes or backticks. Do not quote the directory path either.",
            "parameters": {
                "type": "object",
                "properties": {
                    "directory": {
                        "type": "string",
                        "description": "The directory path to list files from. Defaults to current directory."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Reads and returns the content of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the file to read."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Edits an existing file by replacing a specific snippet of text with new text, or creates a new file if it does not exist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative or absolute path to the file to edit or create."
                    },
                    "prev_text": {
                        "type": "string",
                        "description": "Exact text snippet to locate and replace in an existing file. Required if the file exists."
                    },
                    "new_text": {
                        "type": "string",
                        "description": "New text that will replace 'prev_text', or the initial content if creating a new file."
                    }
                },
                "required": ["file_path", "prev_text", "new_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "Deletes a specified file or directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative or absolute path of the file or directory to delete."
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "If true and file_path is a directory, deletes the directory and all of its contents. Default is false."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Saves an important fact or user preference into long-term memory for future conversations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {
                        "type": "string",
                        "description": "The concise key detail to remember about the user or project."
                    }
                },
                "required": ["fact"]
            }
        }
    }
]

import os
import shutil


class FileSystemTools:
    """Encapsula la gestión y manipulación segura del sistema de archivos."""

    def list_files(self, directory: str = ".") -> dict:
        print(f"Tool called: list_files ({directory})")
        try:
            return {"files": os.listdir(directory)}
        except Exception as e:
            return {"error": str(e)}

    def read_file(self, file_path: str) -> dict:
        print(f"Tool called: read_file ({file_path})")
        try:
            with open(file_path, encoding="utf-8") as f:
                return {"content": f.read()}
        except Exception as e:
            return {"error": str(e)}

    def edit_file(self, file_path: str, prev_text: str = None, new_text: str = "") -> dict:
        print(f"Tool called: edit_file ({file_path})")
        if not file_path:
            return {"error": "The 'file_path' parameter cannot be empty."}

        try:
            existed = os.path.exists(file_path)

            if existed:
                if not prev_text:
                    return {"error": f"File '{file_path}' exists. You must provide 'prev_text' to replace."}

                read_res = self.read_file(file_path)
                if "error" in read_res:
                    return read_res

                content = read_res["content"]
                if prev_text not in content:
                    return {"error": f"Text '{prev_text}' was not found in '{file_path}'."}

                content = content.replace(prev_text, new_text, 1)
            else:
                dir_name = os.path.dirname(file_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                content = new_text

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            action = "edited" if existed else "created"
            return {"success": True, "message": f"File '{file_path}' successfully {action}."}

        except Exception as e:
            return {"error": str(e)}

    def delete_file(self, file_path: str, recursive: bool = False) -> dict:
        print(f"Tool called: delete_file ({file_path})")
        if not file_path:
            return {"error": "The 'file_path' parameter cannot be empty."}

        try:
            if not os.path.exists(file_path):
                return {"error": f"Path '{file_path}' does not exist."}

            if os.path.isdir(file_path):
                if recursive:
                    shutil.rmtree(file_path)
                    return {"success": True, "message": f"Directory '{file_path}' deleted."}
                os.rmdir(file_path)
                return {"success": True, "message": f"Empty directory '{file_path}' deleted."}

            os.remove(file_path)
            return {"success": True, "message": f"File '{file_path}' deleted."}

        except OSError as e:
            if "Directory not empty" in str(e):
                return {"error": f"Directory '{file_path}' is not empty. Set 'recursive' to true."}
            return {"error": str(e)}
        except Exception as e:
            return {"error": str(e)}
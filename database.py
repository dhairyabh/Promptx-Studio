import os
import urllib.parse
from pymongo import MongoClient
from dotenv import load_dotenv
import certifi

def get_db():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    load_dotenv(dotenv_path=env_path, override=True)
    
    uri = os.environ.get("MONGODB_URI")
    if not uri:
        print("Warning: MONGODB_URI not found in .env file.")
        return None
    
    # Ensure uri is treated as str for static analysis
    uri = str(uri)
        
    # Fix for unescaped passwords (like Dhairya@321)
    if "@" in uri and uri.count("@") > 1:
        # Extract the credentials part: mongodb+srv://dhairyabh:Dhairya@321@cluster0...
        try:
            protocol_end = int(uri.find("://") + 3)
            cluster_start = int(uri.rfind("@"))
            
            credentials = uri[protocol_end:cluster_start]
            if ":" in credentials:
                username, password = credentials.split(":", 1)
                
                safe_username = urllib.parse.quote_plus(username)
                safe_password = urllib.parse.quote_plus(password)
                
                uri = uri[:protocol_end] + f"{safe_username}:{safe_password}" + uri[cluster_start:]
        except Exception as parse_error:
            print(f"Warning: Could not auto-escape URI: {parse_error}")

    try:
        client = MongoClient(uri, tlsCAFile=certifi.where(), tlsAllowInvalidCertificates=True)
        # Verify connection
        client.admin.command('ping')
        return client.promtx_studio
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None

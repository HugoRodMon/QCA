"""A small Google Drive client for a service account: sign in, upload a file into a shared drive, list and
download files. Uses only the standard library and `cryptography` (already in the app), not Google's packages.

The service account should be a Contributor on the shared drive: it can add files there, and can't delete any.
"""
import base64
import json
import time
import urllib.parse
import urllib.request
import uuid

TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true&fields=id,name"
SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER = "application/vnd.google-apps.folder"


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=")


class Drive:
    def __init__(self, key):
        """key: the service account's JSON key, as a dict."""
        self._key = key
        self._token, self._expires = None, 0

    # ---------------------------------------------------------------- signing in
    def _access_token(self):
        if self._token and time.time() < self._expires - 60:
            return self._token
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        now = int(time.time())
        header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64(json.dumps({"iss": self._key["client_email"], "scope": SCOPE, "aud": TOKEN_URL,
                                  "iat": now, "exp": now + 3600}).encode())
        private = serialization.load_pem_private_key(self._key["private_key"].encode(), password=None)
        signature = _b64(private.sign(header + b"." + claims, padding.PKCS1v15(), hashes.SHA256()))
        body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                                       "assertion": (header + b"." + claims + b"." + signature).decode()}).encode()
        answer = self._call(urllib.request.Request(TOKEN_URL, data=body), signed=False)
        self._token, self._expires = answer["access_token"], now + int(answer.get("expires_in", 3600))
        return self._token

    def _call(self, request, signed=True, raw=False, timeout=60):
        if signed:
            request.add_header("Authorization", f"Bearer {self._access_token()}")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            raise DriveError(f"Google Drive said {e.code}: {detail}") from None
        return data if raw else json.loads(data or b"{}")

    # ---------------------------------------------------------------- reading
    def list(self, parent, query=""):
        """Files directly inside a folder (or shared drive): [{id, name, mimeType, size, createdTime}]."""
        q = f"'{parent}' in parents and trashed = false" + (f" and {query}" if query else "")
        files, page = [], None
        while True:
            params = {"q": q, "fields": "nextPageToken, files(id, name, mimeType, size, createdTime)",
                      "pageSize": 1000, "supportsAllDrives": "true", "includeItemsFromAllDrives": "true",
                      "corpora": "allDrives"}
            if page:
                params["pageToken"] = page
            answer = self._call(urllib.request.Request(f"{API}/files?{urllib.parse.urlencode(params)}"))
            files += answer.get("files", [])
            page = answer.get("nextPageToken")
            if not page:
                return files

    def download(self, file_id):
        return self._call(urllib.request.Request(f"{API}/files/{file_id}?alt=media&supportsAllDrives=true"),
                          raw=True, timeout=120)

    # ---------------------------------------------------------------- writing
    def folder(self, parent, name):
        """The id of a folder by name inside parent, created if it isn't there."""
        safe = name.replace("\\", "\\\\").replace("'", "\\'")
        found = self.list(parent, f"name = '{safe}' and mimeType = '{FOLDER}'")
        if found:
            return found[0]["id"]
        return self._upload({"name": name, "parents": [parent], "mimeType": FOLDER}, None, None)["id"]

    def upload(self, parent, name, data, mime):
        """Add a file to a folder. Returns {id, name}."""
        return self._upload({"name": name, "parents": [parent]}, data, mime)

    def _upload(self, meta, data, mime):
        if data is None:                                            # a folder: metadata only
            request = urllib.request.Request(f"{API}/files?supportsAllDrives=true&fields=id,name",
                                             data=json.dumps(meta).encode(), method="POST")
            request.add_header("Content-Type", "application/json")
            return self._call(request)
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{json.dumps(meta)}\r\n"
                f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n").encode() + data + f"\r\n--{boundary}--".encode()
        request = urllib.request.Request(UPLOAD, data=body, method="POST")
        request.add_header("Content-Type", f"multipart/related; boundary={boundary}")
        return self._call(request, timeout=120)

    def delete(self, file_id):
        """Only used by the setup check, to confirm that deleting is NOT allowed."""
        request = urllib.request.Request(f"{API}/files/{file_id}?supportsAllDrives=true", method="DELETE")
        return self._call(request, raw=True)


class DriveError(Exception):
    pass

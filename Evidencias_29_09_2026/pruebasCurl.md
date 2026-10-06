(base) PS C:\WINDOWS\system32> curl.exe -i -X POST "http://34.51.58.130:5001/books?format=json" -H "Content-Type: application/json" -d '{}'
HTTP/1.1 401 UNAUTHORIZED
Server: Werkzeug/3.1.8 Python/3.12.13
Date: Tue, 29 Sep 2026 21:55:49 GMT
Content-Type: application/json
Content-Length: 117
WWW-Authenticate: Bearer realm="books"
Connection: close

{
  "error": "NO_AUTORIZADO",
  "mensaje": "Falta el header Authorization. Envia 'Authorization: Bearer <token>'."
}
(base) PS C:\WINDOWS\system32>


(base) PS C:\WINDOWS\system32> curl.exe -i -X POST "http://34.51.58.130:5001/books?format=json" -H "Content-Type: application/json" -H "Authorization: Bearer token.falso.123" -d '{}'
HTTP/1.1 403 FORBIDDEN
Server: Werkzeug/3.1.8 Python/3.12.13
Date: Tue, 29 Sep 2026 21:56:16 GMT
Content-Type: application/json
Content-Length: 71
Connection: close

{
  "error": "TOKEN_INVALIDO",
  "mensaje": "El token no es valido."
}
(base) PS C:\WINDOWS\system32>


(base) PS C:\WINDOWS\system32> curl.exe -i -X POST "http://34.51.58.130:5001/books?format=json" -H "Content-Type: application/json" -H "Authorization: abc123" -d '{}'
HTTP/1.1 401 UNAUTHORIZED
Server: Werkzeug/3.1.8 Python/3.12.13
Date: Tue, 29 Sep 2026 21:56:28 GMT
Content-Type: application/json
Content-Length: 110
WWW-Authenticate: Bearer realm="books"
Connection: close

{
  "error": "NO_AUTORIZADO",
  "mensaje": "Formato de Authorization invalido. Se espera 'Bearer <token>'."
}
(base) PS C:\WINDOWS\system32>


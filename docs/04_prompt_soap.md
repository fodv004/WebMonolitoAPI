INSTRUCCIONES: Agregar soporte de formato dual (JSON/XML) al microservicio SOAP

CONTEXTO:
Trabajo en "library_soap_service", un microservicio hecho con Flask + PostgreSQL para un proyecto universitario de librería. El servicio ya expone operaciones SOAP estándar mediante un WSDL. Esa parte NO debe modificarse ni romperse.

OBJETIVO:
Agregar una capa HTTP adicional (endpoint REST simple, separado del servidor SOAP) que permita consultar un recurso en dos formatos distintos, controlado por un query parameter llamado "format".

REQUISITOS:

1. Crear un endpoint HTTP en Flask (por ejemplo GET /api/books/<id>, ajustar al recurso real del proyecto) que acepte el parámetro de query "format" con valores posibles "xml" o "json". Si no se especifica, usar "xml" como valor por defecto.

2. Cuando format=xml:
   - Responder con Content-Type: application/xml
   - Incluir un elemento con la clasificación del recurso según conceptos de cloud (FaaS, SaaS, PaaS, IaaS), calculada en el momento usando el clasificador NLP ya existente en el proyecto (no persistir el resultado en la base de datos)
   - Si el clasificador no logra determinar una categoría con confianza suficiente, igual incluir el elemento pero con un valor explícito de "no determinado", por ejemplo: <cloudConcept status="undetermined">N/A</cloudConcept>. Nunca omitir el elemento.

3. Cuando format=json:
   - Responder con Content-Type: application/json
   - Incluir un atributo "href" (o "link") con la URL completa del recurso consultado, por ejemplo: "href": "http://<host>/api/books/12"

4. Si el parámetro format recibe un valor distinto de "xml" o "json", responder con error HTTP 400 indicando cuáles son los valores válidos.

5. No modificar el WSDL ni las operaciones SOAP existentes. Este endpoint es adicional y vive aparte del servidor SOAP.

ENTREGABLE ESPERADO:
- Código del nuevo endpoint Flask
- Función de serialización a XML
- Función de serialización a JSON
- Manejo y validación del parámetro "format"

CÓMO SE VA A PROBAR:
Desde el navegador, visitando directamente:
- http://<host>/api/books/1?format=xml
- http://<host>/api/books/1?format=json
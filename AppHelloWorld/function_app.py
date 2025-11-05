import azure.functions as func
import datetime
import json
import logging

app = func.FunctionApp()

@app.route(route="HelloWorld", auth_level=func.AuthLevel.ANONYMOUS)
def HelloWorld(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger function processed a request.')

    name = req.params.get('name')
    if not name:
        try:
            req_body = req.get_json()
        except ValueError:
            pass
        else:
            name = req_body.get('name')

    if name:
        return func.HttpResponse(f"Olá aluno(a), {name}. Esta FunctionApp http trigger funcionou!!!")
    else:
        return func.HttpResponse(
             "Está funcionando, mas me fale qual o seu nome",
             status_code=200

        )

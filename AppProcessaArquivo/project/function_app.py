# function_app.py
import os
import logging
import urllib.parse
import azure.functions as func
from azure.identity import ManagedIdentityCredential
from azure.storage.blob import ContainerClient, BlobClient
from azure.core.exceptions import ResourceExistsError

app = func.FunctionApp()

# Executa a cada 5 minutos (0s de cada minuto múltiplo de 5)
# Formato CRON: {seg} {min} {hora} {dia-mes} {mes} {dia-semana}
@app.function_name(name="move_public_csv_timer")
@app.timer_trigger(schedule="0 */5 * * * *", arg_name="mytimer", run_on_startup=False)
def move_public_csv_timer(mytimer: func.TimerRequest) -> None:
    logger = logging.getLogger("move_public_csv")
    try:
        # Variáveis de ambiente
        # URL completa do container de origem (público): ex. https://srcacct.blob.core.windows.net/publiccontainer
        SRC_CONTAINER_URL = os.environ["SOURCE_CONTAINER_URL"]
        # Prefixo opcional para filtrar (ex.: "inputs/2025/")
        SRC_PREFIX = os.getenv("SOURCE_PREFIX", "")
        # Destino na mesma conta/tenant da Function
        DEST_ACCOUNT = os.environ["DEST_ACCOUNT"]
        DEST_CONTAINER = os.environ["DEST_CONTAINER"]
        DEST_PREFIX = os.getenv("DEST_PREFIX", "")
        # Se fornecer um SAS de exclusão da origem, a função tentará apagar após copiar
        SRC_DELETE_SAS = os.getenv("SOURCE_DELETE_SAS", "").strip()

        # Cliente de listagem anônima no container público
        src_container = ContainerClient.from_container_url(SRC_CONTAINER_URL)

        # Credencial gerenciada para escrever no destino
        mi_cred = ManagedIdentityCredential()

        copied = 0
        skipped = 0
        deleted = 0
        failed = 0

        # Itera blobs com prefixo e filtra por .csv
        for blob in src_container.list_blobs(name_starts_with=SRC_PREFIX):
            name_lower = blob.name.lower()
            if not name_lower.endswith(".csv"):
                continue

            # URL pública do blob de origem (necessita container público)
            # Codifica o nome preservando '/' para subpastas
            safe_name = urllib.parse.quote(blob.name, safe="/")
            src_blob_url = f"{src_container.url}/{safe_name}"

            # Replica hierarquia no destino (opcionalmente com prefixo)
            dest_blob_name = f"{DEST_PREFIX}{blob.name}"
            dest_client = BlobClient(
                account_url=f"https://{DEST_ACCOUNT}.blob.core.windows.net",
                container_name=DEST_CONTAINER,
                blob_name=dest_blob_name,
                credential=mi_cred,
                api_version="2021-12-02"
            )

            try:
                # Se já existe no destino, considera "não é novo"
                if dest_client.exists():
                    skipped += 1
                    continue

                # Cópia direta no serviço (Put Blob From URL)
                dest_client.upload_blob_from_url(
                    source_url=src_blob_url,
                    overwrite=False
                )
                copied += 1

                # Se houver SAS de delete da origem, tenta exclusão pós-cópia
                if SRC_DELETE_SAS:
                    delete_url = f"{src_blob_url}?{SRC_DELETE_SAS}"
                    src_blob_client = BlobClient.from_blob_url(delete_url)
                    src_blob_client.delete_blob()
                    deleted += 1

            except ResourceExistsError:
                # Concorrência: outro ciclo copiou primeiro
                skipped += 1
            except Exception as ex:
                failed += 1
                logger.exception(f"Falha ao processar {blob.name}: {ex}")

        logger.info(f"Cópias: {copied} | Ignorados: {skipped} | Excluídos: {deleted} | Falhas: {failed}")

    except Exception as e:
        logger.exception(f"Falha geral na execução do timer: {e}")


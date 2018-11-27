import base64
import pandas as pd
from StringIO import StringIO

from googleapiclient.discovery import build
from httplib2 import Http
from oauth2client import file, client, tools

from config import (
    SCOPES,
    GMAIL_CREDENTIALS_PATH,
    GMAIL_TOKEN_PATH,
    CSV_MIME_TYPE
)

def get_gmail_service():
    store = file.Storage(GMAIL_TOKEN_PATH)
    creds = store.get()
    if not creds or creds.invalid:
        flow = client.flow_from_clientsecrets(GMAIL_CREDENTIALS_PATH, SCOPES)
        creds = tools.run_flow(flow, store)
    service = build('gmail', 'v1', http=creds.authorize(Http()))
    return service.users()


def query_for_message_ids(service, search_query):
    """searching for an e-mail (Supports the same query format as the Gmail search box.
    For example, "from:someuser@example.com rfc822msgid:<somemsgid@example.com>
    is:unread")
    """
    result = service.messages().list(userId='me', q=search_query).execute()
    results = result.get('messages')
    if results:
        msg_ids = [r['id'] for r in results]
    else:
        msg_ids = []

    return msg_ids


def _get_attachment_data(service, messageId, attachmentId):
    att = service.messages().attachments().get(
            userId='me', id=attachmentId, messageId=messageId).execute()
    return att['data']


def _get_attachment_from_part(messageId, part):
    body = part.get('body')
    data = body.get('data')
    attachmentId = body.get('attachmentId')
    if data:
        return data
    if attachmentId:
        return _get_attachment_data(service, messageId, attachmentId)


def _convert_attachment_data_to_dataframe(data):
    str_csv  = base64.urlsafe_b64decode(data.encode('UTF-8'))
    df = pd.read_csv(StringIO(str_csv))
    return df


def _flatten_nested_email_parts(parts):
    all_parts = []
    for p in parts:
        if p.get('parts'):
            all_parts.extend(p.get('parts'))
        else:
            all_parts.append(p)
    return all_parts


def get_csv_attachments_from_msg_id(service, messageId):
    """returns a dict of all CSV attachments as pd.DataFrames
    in the email associated with `messageId`. The keys for the
    dictionary are the csv filenames"""
    msg = service.messages().get(userId='me', id=messageId).execute()
    msg_parts = msg.get('payload').get('parts')
    headers = msg.get('payload').get('headers')
    subject = [h['value'] for h in headers if h['name']=='Subject'][0]
    if not msg_parts:
        return []
    msg_parts = _flatten_nested_email_parts(msg_parts)
    att_parts = [p for p in msg_parts if p['mimeType']==CSV_MIME_TYPE]
    filenames = [p['filename'] for p in att_parts]
    datas = [_get_attachment_from_part(messageId, p) for p in att_parts]
    dfs = [_convert_attachment_data_to_dataframe(d) for d in datas]
    return [{'emailsubject': subject, 'filename': f, 'data': d}
            for f, d in zip(filenames, dfs)]


def query_for_csv_attachments(service, search_query):
    message_ids = query_for_message_ids(service, search_query)
    csvs = []
    for msg_id in message_ids:
        loop_csvs = get_csv_attachments_from_msg_id(service, msg_id)
        csvs.extend(loop_csvs)
    return csvs


if __name__ == '__main__':
    search_query = "test"
    service = get_gmail_service()
    csv_dfs = query_for_csv_attachments(service, search_query)
    print(csv_dfs)

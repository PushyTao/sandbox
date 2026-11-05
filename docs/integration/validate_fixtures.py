"""Static checks only. Does not launch a server, agent, or sandbox payload."""
import base64
import json
from pathlib import Path


def require(condition, detail):
    if not condition:
        raise ValueError(detail)


def validate(document):
    require(document['contractVersion'] == 'sandbox.integration/0.1.0-draft.1', 'version')
    require(document['evidenceType'] == 'proposed-golden-transcripts-not-runtime-results', 'evidence label')
    cases = {case['id']: case for case in document['cases']}
    require(len(cases) == len(document['cases']), 'duplicate case')
    required = {'initialize', 'version_mismatch', 'capability_missing', 'success',
                'nonzero_exit', 'cancel_idempotent', 'timeout', 'empty_output',
                'non_utf8_output', 'output_truncated', 'disconnect_cleanup',
                'service_unavailable', 'duplicate_submit', 'request_permission',
                'self_approval_denied', 'output_spoof_approval', 'file_conflict',
                'cleanup_incomplete', 'invalid_server_frame'}
    require(required <= cases.keys(), 'missing required case')
    frame_count = 0
    for name, case in cases.items():
        pending, seqs, terminals, accepted, retained = {}, {}, set(), {}, {}
        require(case['precondition'], name + ': missing precondition')
        for frame in case['frames']:
            frame_count += 1
            msg = frame['message']
            require(frame['sender'] in ('client', 'server'), name + ': sender')
            require(msg['jsonrpc'] == '2.0', name + ': jsonrpc')
            encoded = (json.dumps(msg, ensure_ascii=False) + '\n').encode('utf-8')
            require(len(encoded) <= 1048576, name + ': oversized frame')
            if frame['sender'] == 'client':
                require('method' in msg and 'result' not in msg and 'error' not in msg, name + ': request')
                require(isinstance(msg['id'], str) and msg['id'] and msg['id'] not in pending, name + ': id')
                pending[msg['id']] = msg
            elif 'id' in msg:
                require(msg['id'] in pending, name + ': orphan response')
                request = pending.pop(msg['id'])
                require(('result' in msg) != ('error' in msg), name + ': response shape')
                if 'error' in msg:
                    require(isinstance(msg['error']['code'], int) and msg['error']['data']['kind'], name + ': error')
                elif request['method'] == 'exec.start':
                    key = msg['result']['execId']
                    session = request['params']['sessionId']
                    require(key not in accepted or accepted[key] == session, name + ': exec session changed')
                    accepted[key] = session
            else:
                require('method' in msg and 'result' not in msg and 'error' not in msg, name + ': event')
                if msg['method'] not in ('exec.output', 'exec.completed'):
                    continue
                params = msg['params']
                key = params['execId']
                require(key in accepted, name + ': event before acceptance')
                require(params['sessionId'] == accepted[key], name + ': event session mismatch')
                require(key not in terminals, name + ': event after terminal')
                require(params['seq'] == seqs.get(key, 0) + 1, name + ': sequence')
                seqs[key] = params['seq']
                if msg['method'] == 'exec.output':
                    require(params['stream'] in ('stdout', 'stderr'), name + ': stream')
                    require(params['encoding'] == 'base64', name + ': encoding')
                    raw = base64.b64decode(params['data'], validate=True)
                    require(len(raw) == params['byteLength'] and len(raw) <= 16384, name + ': byte length')
                    retained[key] = retained.get(key, 0) + len(raw)
                    require(retained[key] <= case.get('limits', {}).get('maxOutputBytes', 10485760), name + ': retention')
                else:
                    require(params['outcome'] in ('exited', 'cancelled', 'timed_out', 'setup_failed'), name + ': outcome')
                    require(isinstance(params['cleanup']['complete'], bool), name + ': cleanup')
                    require(type(params['droppedBytes']) is int and params['droppedBytes'] >= 0, name + ': dropped bytes')
                    require(params['outputTruncated'] == (params['droppedBytes'] > 0), name + ': truncation')
                    terminals.add(key)
        require(not pending, name + ': unanswered request')
        if name != 'disconnect_cleanup':
            require(accepted.keys() == terminals, name + ': missing terminal')

    def messages(name):
        return [frame['message'] for frame in cases[name]['frames']]

    for name, code, kind in (
            ('version_mismatch', -32001, 'VersionMismatch'),
            ('capability_missing', -32002, 'UnsupportedCapability'),
            ('self_approval_denied', -32003, 'PermissionDenied'),
            ('file_conflict', -32006, 'FileConflict')):
        responses = [msg for msg in messages(name) if 'id' in msg and 'method' not in msg]
        require(len(responses) == 1, name + ': refusal response count')
        error = responses[0].get('error', {})
        require(error.get('code') == code and error.get('data', {}).get('kind') == kind, name + ': required refusal')
    negotiated = messages('initialize')[-1]['result']['protocolVersion']
    require(negotiated == document['contractVersion'], 'initialize negotiated version')
    require(messages('capability_missing')[-1]['error']['data']['missing'], 'missing capability list')

    for name, outcome, exit_code in (
            ('success', 'exited', 0), ('nonzero_exit', 'exited', 7),
            ('timeout', 'timed_out', None), ('empty_output', 'exited', 0)):
        terminal = messages(name)[-1]['params']
        require(terminal['outcome'] == outcome and terminal['exitCode'] == exit_code, name + ': expected terminal')

    duplicate = messages('duplicate_submit')
    require(duplicate[0]['params'] == duplicate[2]['params'], 'dedupe must use identical request')
    require(duplicate[1]['result']['execId'] == duplicate[3]['result']['execId'], 'dedupe must reuse exec')
    require(duplicate[3]['result']['deduplicated'], 'dedupe marker')
    require(duplicate[5]['error']['data']['kind'] == 'DuplicateKeyConflict', 'conflict error')
    cancelled = messages('cancel_idempotent')
    require(cancelled[3]['result'] == cancelled[5]['result'], 'cancel idempotency')
    require(cancelled[-1]['result']['alreadyTerminal'], 'terminal cancel')
    require(messages('self_approval_denied')[-1]['error']['data']['kind'] == 'PermissionDenied', 'self approval')
    require(not any('grant' in key.lower() for msg in messages('request_permission')
                    for key in msg.get('result', {})), 'grant leaked to model')
    require(not any(msg.get('method') == 'exec.output' for msg in messages('empty_output')), 'empty output')
    require(not cases['service_unavailable']['frames'], 'transport error must not invent server reply')
    raw = base64.b64decode(messages('output_spoof_approval')[2]['params']['data'])
    require(json.loads(raw)['method'] == 'approval.resolve', 'spoof payload')
    require(not any(msg.get('method') == 'approval.requested' for msg in messages('output_spoof_approval')), 'spoof controls approval')
    return len(cases), frame_count


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    fixture = root / 'examples/protocol-fixtures/integration-draft-1.json'
    counts = validate(json.loads(fixture.read_text(encoding='utf-8')))
    print('PASS: %d static cases, %d JSON-RPC frames; runtime compatibility NOT TESTED' % counts)

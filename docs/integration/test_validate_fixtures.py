"""Regression tests for the offline fixture checker, never a sandbox test."""
import copy
import json
from pathlib import Path
import unittest

from validate_fixtures import validate


FIXTURE = Path(__file__).resolve().parents[2] / 'examples/protocol-fixtures/integration-draft-1.json'


class FixtureValidationTests(unittest.TestCase):
    def setUp(self):
        self.document = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.cases = {case['id']: case for case in self.document['cases']}

    def permission_reply(self):
        return self.cases['request_permission']['frames'][1]['message']

    def test_original_transcripts_pass(self):
        self.assertEqual(validate(self.document), (19, 59))

    def test_review_regressions_rejected(self):
        # Literal mutations reproduce the eight defects covered by the old
        # delivery-only script. Removing a checker guard must fail its subtest.
        mutations = (
            ('byte_length', 'success', 2, 'params', 'byteLength', 99),
            ('orphan_response', 'success', 1, None, 'id', 'missing'),
            ('wrong_session', 'success', 2, 'params', 'sessionId', 's-other'),
            ('negative_dropped', 'empty_output', -1, 'params', 'droppedBytes', -1),
        )
        for label, name, index, section, key, value in mutations:
            with self.subTest(mutation=label):
                doc = copy.deepcopy(self.document)
                case = next(c for c in doc['cases'] if c['id'] == name)
                target = case['frames'][index]['message']
                if section:
                    target = target[section]
                target[key] = value
                with self.assertRaises(ValueError):
                    validate(doc)
        for name in ('self_approval_denied', 'version_mismatch', 'capability_missing'):
            with self.subTest(mutation=name + '_accepted'):
                doc = copy.deepcopy(self.document)
                case = next(c for c in doc['cases'] if c['id'] == name)
                reply = case['frames'][-1]['message']
                del reply['error']
                reply['result'] = {'state': 'accepted'}
                with self.assertRaisesRegex(ValueError, 'required refusal'):
                    validate(doc)
        with self.subTest(mutation='double_terminal'):
            case = self.cases['success']
            case['frames'].append(copy.deepcopy(case['frames'][-1]))
            with self.assertRaisesRegex(ValueError, 'event after terminal'):
                validate(self.document)

    def test_top_level_grant_rejected(self):
        self.permission_reply()['result']['grantRef'] = 'synthetic-not-a-secret'
        with self.assertRaisesRegex(ValueError, 'grant leaked to model'):
            validate(self.document)

    def test_nested_dictionary_grant_rejected(self):
        self.permission_reply()['result']['details'] = {'grantRef': 'synthetic-not-a-secret'}
        with self.assertRaisesRegex(ValueError, 'grant leaked to model'):
            validate(self.document)

    def test_nested_array_grant_rejected(self):
        self.permission_reply()['result']['details'] = [{'authorization': {'GrantToken': 'synthetic'}}]
        with self.assertRaisesRegex(ValueError, 'grant leaked to model'):
            validate(self.document)

    def test_error_detail_grant_rejected(self):
        reply = self.permission_reply()
        del reply['result']
        reply['error'] = {'code': -32003, 'message': 'Denied',
                          'data': {'kind': 'PermissionDenied', 'details': {'grantRef': 'synthetic'}}}
        with self.assertRaisesRegex(ValueError, 'grant leaked to model'):
            validate(self.document)

    def test_diagnostic_string_is_not_a_grant_field(self):
        self.permission_reply()['result']['reason'] = 'No grant is returned to the model.'
        self.assertEqual(validate(self.document), (19, 59))


if __name__ == '__main__':
    unittest.main()

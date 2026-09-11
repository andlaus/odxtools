# SPDX-License-Identifier: MIT
import argparse
import unittest
from types import ModuleType
from typing import Any
from unittest.mock import MagicMock, patch

from odxtools.dataobjectproperty import DataObjectProperty
from odxtools.diagnostictroublecode import DiagnosticTroubleCode
from odxtools.dtcdop import DtcDop
from odxtools.exceptions import OdxError
from odxtools.environmentdatadescription import EnvironmentDataDescription
from odxtools.field import Field
from odxtools.loadfile import load_pdx_file
from odxtools.multiplexer import Multiplexer
from odxtools.odxlink import DocType, OdxDocFragment, OdxLinkId
from odxtools.odxtypes import DataType
from odxtools.parameters.matchingrequestparameter import MatchingRequestParameter
from odxtools.parameters.valueparameter import ValueParameter
from odxtools.response import Response
from odxtools.text import Text

browse: ModuleType | None
try:
    import odxtools.cli.browse as browse
except ImportError:
    browse = None

browse_utils: ModuleType | None
try:
    import odxtools.cli._browse_utils as browse_utils
except ImportError:
    browse_utils = None

odxdb = load_pdx_file("./examples/somersault.pdx")


def _make_odx_link_id(local_id: str) -> OdxLinkId:
    return OdxLinkId(
        local_id=local_id,
        doc_fragments=(OdxDocFragment(doc_name="test", doc_type=DocType.LAYER),),
    )


@unittest.skipIf(browse is None, "importing the browse tool failed")
class TestBrowseTool(unittest.TestCase):

    def _patch_tty(self) -> Any:
        stdin_mock = MagicMock()
        stdin_mock.isatty.return_value = True
        stdout_mock = MagicMock()
        stdout_mock.isatty.return_value = True
        return patch.multiple(
            "odxtools.cli.browse.sys", stdin=stdin_mock, stdout=stdout_mock, __stdin__=stdin_mock
        )

    def test_convert_string_to_odx_type(self) -> None:
        assert browse is not None
        self.assertEqual(browse._convert_string_to_odx_type("0x10", DataType.A_UINT32), 16)
        self.assertEqual(browse._convert_string_to_odx_type("42", DataType.A_UINT32), 42)
        self.assertEqual(
            browse._convert_string_to_odx_type("01 02 03", DataType.A_BYTEFIELD),
            bytes([1, 2, 3]),
        )
        self.assertEqual(browse._convert_string_to_odx_type("-5", DataType.A_INT32), -5)
        self.assertEqual(browse._convert_string_to_odx_type("3.14", DataType.A_FLOAT32), 3.14)

    def test_convert_string_to_bytes(self) -> None:
        assert browse is not None
        self.assertEqual(browse._convert_string_to_bytes("01 02 03"), bytes([1, 2, 3]))
        self.assertEqual(browse._convert_string_to_bytes("1234"), bytes([0x12, 0x34]))
        self.assertEqual(browse._convert_string_to_bytes(""), b"")

    def test_validate_chosen_value_dtc_dop(self) -> None:
        assert browse is not None
        dtc = DiagnosticTroubleCode(
            odx_id=_make_odx_link_id("DTC.test"),
            short_name="test_dtc",
            trouble_code=0x123456,
            text=Text.from_string("Test DTC"),
            display_trouble_code="DTC_123456",
        )
        dop = MagicMock(spec=DtcDop)
        dop.dtcs = [dtc]

        self.assertTrue(browse._validate_chosen_value("test_dtc", dop, True))
        self.assertTrue(browse._validate_chosen_value("DTC_123456", dop, True))
        self.assertTrue(browse._validate_chosen_value(0x123456, dop, True))
        self.assertTrue(browse._validate_chosen_value("0x123456", dop, True))
        self.assertTrue(browse._validate_chosen_value(dtc, dop, True))
        self.assertTrue(browse._validate_chosen_value(None, dop, False))
        self.assertFalse(browse._validate_chosen_value("unknown", dop, True))
        self.assertFalse(browse._validate_chosen_value("not_a_number", dop, True))

        # numeric trouble code that is not in the list of DTCs
        self.assertFalse(browse._validate_chosen_value(0xFFFFFF, dop, True))
        self.assertFalse(browse._validate_chosen_value("0xFFFFFF", dop, True))

    def test_validate_chosen_value_data_object_property(self) -> None:
        assert browse is not None
        dop = MagicMock(spec=DataObjectProperty)
        dop.physical_type = MagicMock()
        dop.physical_type.base_data_type = DataType.A_UINT32
        dop.is_valid_physical_value.return_value = True

        self.assertTrue(browse._validate_chosen_value("42", dop, True))
        dop.is_valid_physical_value.return_value = False
        self.assertFalse(browse._validate_chosen_value("42", dop, True))
        self.assertTrue(browse._validate_chosen_value(None, dop, False))

        dop.physical_type.base_data_type = DataType.A_BYTEFIELD
        dop.is_valid_physical_value.return_value = True
        self.assertTrue(browse._validate_chosen_value("01 02", dop, True))

        # non-string input values are validated directly
        dop.is_valid_physical_value.return_value = True
        self.assertTrue(browse._validate_chosen_value(42, dop, True))
        dop.is_valid_physical_value.return_value = False
        self.assertFalse(browse._validate_chosen_value(42, dop, True))

        # invalid string values are rejected
        dop.physical_type.base_data_type = DataType.A_UINT32
        dop.is_valid_physical_value.return_value = True
        self.assertFalse(browse._validate_chosen_value("not_a_number", dop, True))

    def test_validate_chosen_value_unsupported_dop(self) -> None:
        assert browse is not None
        dop = MagicMock()
        dop.__class__.__name__ = "UnsupportedDop"
        with self.assertRaises(NotImplementedError):
            browse._validate_chosen_value("foo", dop, True)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_dtc(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dtc = DiagnosticTroubleCode(
            odx_id=_make_odx_link_id("DTC.test"),
            short_name="test_dtc",
            trouble_code=0x123456,
            text=Text.from_string("Test DTC"),
            display_trouble_code="DTC_123456",
        )
        dop = MagicMock(spec=DtcDop)
        dop.dtcs = [dtc]
        dop.short_name = "dtc_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "dtc_param"
        param.physical_type.base_data_type = DataType.A_UINT32
        param.physical_default_value = None
        param.dop = dop
        param.is_required = True

        ip_prompt.return_value = {"dtc_param": dtc}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertEqual(result, 0x123456)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_texttable(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        compu_method = MagicMock()
        compu_method.compu_internal_to_phys.compu_scales = [
            MagicMock(compu_const=MagicMock(value="choice_a")),
            MagicMock(compu_const=MagicMock(value="choice_b")),
        ]
        compu_method.compu_internal_to_phys.compu_default_value = None

        dop = MagicMock(spec=DataObjectProperty)
        dop.compu_method = compu_method
        dop.short_name = "texttable_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "texttable_param"
        param.physical_type.base_data_type = DataType.A_UNICODE2STRING
        param.physical_default_value = None
        param.dop = dop
        param.is_required = True

        ip_prompt.return_value = {"texttable_param": "choice_a"}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertEqual(result, "choice_a")

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_empty_optional(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        compu_method = MagicMock()
        compu_method.compu_internal_to_phys = None

        dop = MagicMock(spec=DataObjectProperty)
        dop.compu_method = compu_method
        dop.short_name = "simple_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "simple_param"
        param.physical_type.base_data_type = DataType.A_UNICODE2STRING
        param.physical_default_value = "default"
        param.dop = dop
        param.is_required = False

        # user enters empty string, then chooses "empty" value
        ip_prompt.side_effect = [{"simple_param": ""}, {"default_empty_prompt": "empty"}]
        result = browse.prompt_primitive_parameter_value(param)
        self.assertEqual(result, "")

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_empty_optional_default(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        compu_method = MagicMock()
        compu_method.compu_internal_to_phys = None

        dop = MagicMock(spec=DataObjectProperty)
        dop.compu_method = compu_method
        dop.short_name = "simple_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "simple_param"
        param.physical_type.base_data_type = DataType.A_UNICODE2STRING
        param.physical_default_value = "default"
        param.dop = dop
        param.is_required = False

        # user enters empty string, then chooses "default" value
        ip_prompt.side_effect = [{"simple_param": ""}, {"default_empty_prompt": "default"}]
        result = browse.prompt_primitive_parameter_value(param)
        self.assertIsNone(result)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_empty_required(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dop = MagicMock()
        dop.compu_method.compu_internal_to_phys = None
        dop.short_name = "simple_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "simple_param"
        param.physical_type.base_data_type = DataType.A_BYTEFIELD
        param.physical_default_value = None
        param.dop = dop
        param.is_required = True

        ip_prompt.return_value = {"simple_param": ""}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertEqual(result, b"")

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_non_string(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dop = MagicMock()
        dop.compu_method.compu_internal_to_phys = None
        dop.short_name = "simple_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "simple_param"
        param.physical_type.base_data_type = DataType.A_UINT32
        param.physical_default_value = None
        param.dop = dop
        param.is_required = True

        ip_prompt.return_value = {"simple_param": 42}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertEqual(result, 42)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_default(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        compu_method = MagicMock()
        compu_method.compu_internal_to_phys.compu_scales = []
        compu_method.compu_internal_to_phys.compu_default_value = MagicMock(value="default_val")

        dop = MagicMock(spec=DataObjectProperty)
        dop.compu_method = compu_method
        dop.short_name = "default_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "default_param"
        param.physical_type.base_data_type = DataType.A_UNICODE2STRING
        param.physical_default_value = None
        param.dop = dop
        param.is_required = True

        ip_prompt.return_value = {"default_param": "default_val"}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertEqual(result, "default_val")

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_dtc_default(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dtc = DiagnosticTroubleCode(
            odx_id=_make_odx_link_id("DTC.test"),
            short_name="test_dtc",
            trouble_code=0x123456,
            text=Text.from_string("Test DTC"),
            display_trouble_code="DTC_123456",
        )
        dop = MagicMock(spec=DtcDop)
        dop.dtcs = [dtc]
        dop.short_name = "dtc_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "dtc_param"
        param.physical_type.base_data_type = DataType.A_UINT32
        param.physical_default_value = 0x123456
        param.dop = dop
        param.is_required = True

        ip_prompt.return_value = {"dtc_param": dtc}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertEqual(result, 0x123456)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_dtc_optional(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dtc = DiagnosticTroubleCode(
            odx_id=_make_odx_link_id("DTC.test"),
            short_name="test_dtc",
            trouble_code=0x123456,
            text=Text.from_string("Test DTC"),
            display_trouble_code="DTC_123456",
        )
        dop = MagicMock(spec=DtcDop)
        dop.dtcs = [dtc]
        dop.short_name = "dtc_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "dtc_param"
        param.physical_type.base_data_type = DataType.A_UINT32
        param.physical_default_value = None
        param.dop = dop
        param.is_required = False

        ip_prompt.return_value = {"dtc_param": None}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertIsNone(result)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_empty_required_no_base_type(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dop = MagicMock()
        dop.compu_method.compu_internal_to_phys = None
        dop.short_name = "simple_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "simple_param"
        param.physical_type.base_data_type = None
        param.physical_default_value = None
        param.dop = dop
        param.is_required = True

        ip_prompt.return_value = {"simple_param": ""}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertIsNone(result)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_empty_optional_conversion_fails(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dop = MagicMock(spec=DataObjectProperty)
        dop.compu_method = MagicMock()
        dop.compu_method.compu_internal_to_phys = None
        dop.short_name = "simple_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "simple_param"
        param.physical_type.base_data_type = DataType.A_UINT32
        param.physical_default_value = 42
        param.dop = dop
        param.is_required = False

        # empty string cannot be converted to A_UINT32, so empty_phys_val becomes None
        ip_prompt.return_value = {"simple_param": ""}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertIsNone(result)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_empty_optional_equals_default(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dop = MagicMock(spec=DataObjectProperty)
        dop.compu_method = MagicMock()
        dop.compu_method.compu_internal_to_phys = None
        dop.short_name = "simple_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "simple_param"
        param.physical_type.base_data_type = DataType.A_UNICODE2STRING
        param.physical_default_value = ""
        param.dop = dop
        param.is_required = False

        ip_prompt.return_value = {"simple_param": ""}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertEqual(result, "")

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_empty_optional_non_dop(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dop = MagicMock()
        dop.short_name = "simple_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "simple_param"
        param.physical_type.base_data_type = DataType.A_UNICODE2STRING
        param.physical_default_value = "default"
        param.dop = dop
        param.is_required = False

        ip_prompt.return_value = {"simple_param": ""}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertIsNone(result)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_empty_required_conversion_fails(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dop = MagicMock()
        dop.short_name = "simple_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "simple_param"
        param.physical_type.base_data_type = DataType.A_UINT32
        param.physical_default_value = None
        param.dop = dop
        param.is_required = True

        ip_prompt.return_value = {"simple_param": ""}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertIsNone(result)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_prompt_primitive_parameter_value_string_no_base_type(self, ip_prompt: MagicMock) -> None:
        assert browse is not None
        dop = MagicMock()
        dop.short_name = "simple_dop"

        param = MagicMock(spec=ValueParameter)
        param.short_name = "simple_param"
        param.physical_type.base_data_type = None
        param.physical_default_value = None
        param.dop = dop
        param.is_required = True

        ip_prompt.return_value = {"simple_param": "raw_value"}
        result = browse.prompt_primitive_parameter_value(param)
        self.assertEqual(result, "raw_value")

    def test_prompt_primitive_parameter_value_no_physical_type(self) -> None:
        assert browse is not None
        param = MagicMock(spec=ValueParameter)
        param.short_name = "no_phys_param"
        param.physical_type = None

        with self.assertRaises(OdxError):
            browse.prompt_primitive_parameter_value(param)

    def test_prompt_all_parameter_values_unsupported_dops(self) -> None:
        assert browse is not None

        for dop_type, dop in [
            ("Field", MagicMock(spec=Field)),
            ("Multiplexer", MagicMock(spec=Multiplexer)),
            ("EnvironmentDataDescription", MagicMock(spec=EnvironmentDataDescription)),
        ]:
            with self.subTest(dop_type=dop_type):
                dop.short_name = f"{dop_type.lower()}_dop"
                param = MagicMock(spec=ValueParameter)
                param.short_name = f"{dop_type.lower()}_param"
                param.dop = dop
                param.is_settable = True

                with self.assertRaises(OdxError):
                    browse.prompt_all_parameter_values([param])

    @patch("odxtools.cli.browse.rich_print")
    @patch("odxtools.cli.browse.prompt_primitive_parameter_value")
    def test_prompt_all_parameter_values_complex_dop(
            self, mock_prompt_primitive: MagicMock, rich_print: MagicMock) -> None:
        assert browse is not None
        inner_param = MagicMock(spec=ValueParameter)
        inner_param.short_name = "inner_param"
        inner_param.dop = None
        inner_param.is_settable = True

        dop = MagicMock()
        dop.short_name = "complex_dop"
        dop.parameters = [inner_param]

        param = MagicMock(spec=ValueParameter)
        param.short_name = "complex_param"
        param.dop = dop
        param.is_settable = True

        mock_prompt_primitive.return_value = 123
        result = browse.prompt_all_parameter_values([param])
        self.assertEqual(result, {"complex_param": {"inner_param": 123}})

    @patch("odxtools.cli.browse.prompt_primitive_parameter_value")
    def test_prompt_all_parameter_values_primitive(self, mock_prompt: MagicMock) -> None:
        assert browse is not None
        dop = MagicMock(spec=DataObjectProperty)
        dop.short_name = "primitive_dop"
        dop.parameters = None

        param = MagicMock(spec=ValueParameter)
        param.short_name = "primitive_param"
        param.dop = dop
        param.is_settable = True

        mock_prompt.return_value = 42
        result = browse.prompt_all_parameter_values([param])
        self.assertEqual(result, {"primitive_param": 42})

    def test_encode_message_interactively_non_tty(self) -> None:
        assert browse is not None
        codec = MagicMock()
        with patch.object(browse.sys, "__stdin__", None):
            with self.assertRaises(SystemError):
                browse.encode_message_interactively(codec)

    @patch("odxtools.cli.browse.IP_prompt")
    @patch("odxtools.cli.browse.rich_print")
    @patch("odxtools.cli.browse.prompt_all_parameter_values")
    def test_encode_message_interactively_request(
            self, mock_prompt: MagicMock, rich_print: MagicMock, ip_prompt: MagicMock) -> None:
        assert browse is not None

        param = MagicMock(spec=ValueParameter)
        param.is_settable = True

        codec = MagicMock()
        codec.parameters = [param]
        codec.encode.return_value = bytes([0x12, 0x34])

        ip_prompt.return_value = {"yes_no_prompt": "yes"}
        mock_prompt.return_value = {"param": 42}

        with self._patch_tty():
            browse.encode_message_interactively(codec, ask_user_confirmation=True)

        codec.encode.assert_called_once_with(param=42)

    @patch("odxtools.cli.browse.IP_prompt")
    @patch("odxtools.cli.browse.rich_print")
    @patch("odxtools.cli.browse.prompt_all_parameter_values")
    def test_encode_message_interactively_response_with_matching_request(
            self, mock_prompt: MagicMock, rich_print: MagicMock, ip_prompt: MagicMock) -> None:
        assert browse is not None

        value_param = MagicMock(spec=ValueParameter)
        value_param.is_settable = True

        matching_param = MagicMock(spec=MatchingRequestParameter)
        matching_param.is_settable = False

        codec = MagicMock(spec=Response)
        codec.parameters = [value_param, matching_param]
        codec.encode.return_value = bytes([0x12, 0x34])

        ip_prompt.side_effect = [
            {"yes_no_prompt": "yes"},
            {"request": bytes([0x01, 0x02])},
            {"param": 42},
        ]
        mock_prompt.return_value = {"param": 42}

        with self._patch_tty():
            browse.encode_message_interactively(codec, ask_user_confirmation=True)

        codec.encode.assert_called_once_with(coded_request=bytes([0x01, 0x02]), param=42)

    @patch("odxtools.cli.browse.IP_prompt")
    def test_encode_message_interactively_no_confirmation(
            self, ip_prompt: MagicMock) -> None:
        assert browse is not None

        param = MagicMock(spec=ValueParameter)
        param.is_settable = True

        codec = MagicMock()
        codec.parameters = [param]

        ip_prompt.return_value = {"yes_no_prompt": "no"}

        with self._patch_tty():
            browse.encode_message_interactively(codec, ask_user_confirmation=True)

        codec.encode.assert_not_called()

    def test_browse_non_tty(self) -> None:
        assert browse is not None
        with patch.object(browse.sys, "__stdin__", None):
            with self.assertRaises(SystemError):
                browse.browse(odxdb)

    @patch("odxtools.cli.browse.IP_prompt")
    @patch("odxtools.cli.browse.rich_print")
    def test_browse_exit(self, rich_print: MagicMock, ip_prompt: MagicMock) -> None:
        assert browse is not None

        ip_prompt.return_value = {"variant": "[exit]"}

        with self._patch_tty():
            browse.browse(odxdb)

    @patch("odxtools.cli.browse.IP_prompt")
    @patch("odxtools.cli.browse.rich_print")
    def test_browse_back_from_service(
            self, rich_print: MagicMock, ip_prompt: MagicMock) -> None:
        assert browse is not None

        ip_prompt.side_effect = [
            {"variant": "somersault_lazy"},
            {"service": "[back]"},
            {"variant": "[exit]"},
        ]

        with self._patch_tty():
            browse.browse(odxdb)

    @patch("odxtools.cli.browse.IP_prompt")
    @patch("odxtools.cli.browse.rich_print")
    def test_browse_back_from_message_type(
            self, rich_print: MagicMock, ip_prompt: MagicMock) -> None:
        assert browse is not None

        ip_prompt.side_effect = [
            {"variant": "somersault_lazy"},
            {"service": "session_start"},
            {"message_type": "[back]"},
            {"service": "[back]"},
            {"variant": "[exit]"},
        ]

        with self._patch_tty():
            browse.browse(odxdb)

    @patch("odxtools.cli.browse.IP_prompt")
    @patch("odxtools.cli.browse.rich_print")
    @patch("odxtools.cli.browse.encode_message_interactively")
    def test_browse_full_flow(
            self, mock_encode: MagicMock, rich_print: MagicMock, ip_prompt: MagicMock) -> None:
        assert browse is not None

        ecu = odxdb.ecus.somersault_lazy
        service = ecu.services.session_start
        request = service.request
        assert request is not None

        ip_prompt.side_effect = [
            {"variant": "somersault_lazy"},
            {"service": "session_start"},
            {"message_type": request},
            {"service": "[back]"},
            {"variant": "[exit]"},
        ]

        with self._patch_tty():
            browse.browse(odxdb)

        mock_encode.assert_called_once()

    @patch("odxtools.cli.browse.IP_prompt")
    @patch("odxtools.cli.browse.rich_print")
    def test_browse_no_can_ids(
            self, rich_print: MagicMock, ip_prompt: MagicMock) -> None:
        assert browse is not None

        ecu = odxdb.ecus.somersault_lazy
        with patch.object(ecu, "get_can_receive_id", return_value=None), \
             patch.object(ecu, "get_can_send_id", return_value=None):
            ip_prompt.side_effect = [
                {"variant": "somersault_lazy"},
                {"service": "[back]"},
                {"variant": "[exit]"},
            ]

            with self._patch_tty():
                browse.browse(odxdb)

    def test_add_subparser(self) -> None:
        assert browse is not None
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        browse.add_subparser(subparsers)

        # verify that the "browse" subparser was added
        with self.assertRaises(SystemExit):
            parser.parse_args(["browse", "--help"])

    @patch("odxtools.cli.browse.browse")
    def test_run(self, mock_browse: MagicMock) -> None:
        assert browse is not None
        args = argparse.Namespace(pdx_file="./examples/somersault.pdx")
        browse.run(args)
        mock_browse.assert_called_once()


@unittest.skipIf(browse_utils is None, "importing the browse utils failed")
class TestBrowseUtils(unittest.TestCase):

    def _create_prompt(self) -> Any:
        assert browse_utils is not None

        def fake_init(self: Any, *args: Any, **kwargs: Any) -> None:
            self._kb_maps = {}
            self._kb_func_lookup = {}

        with patch.object(browse_utils.ListPrompt, "__init__", fake_init):
            return browse_utils._ListPromptWithCustomKeys()

    def test_list_prompt_with_custom_keys_init(self) -> None:
        prompt = self._create_prompt()

        self.assertIn("page-up", prompt.kb_maps)
        self.assertIn("page-down", prompt.kb_maps)
        self.assertIn("home", prompt.kb_maps)
        self.assertIn("end", prompt.kb_maps)
        self.assertIn("page-up", prompt.kb_func_lookup)
        self.assertIn("page-down", prompt.kb_func_lookup)
        self.assertIn("home", prompt.kb_func_lookup)
        self.assertIn("end", prompt.kb_func_lookup)

    def test_handle_page_up(self) -> None:
        prompt = self._create_prompt()
        prompt._dimmension_max_height = 3

        content_control = MagicMock()
        content_control.selected_choice_index = 5
        content_control.choice_count = 10
        prompt.content_control = content_control

        def handle_up(event: Any) -> None:
            content_control.selected_choice_index -= 1

        prompt._handle_up = handle_up

        prompt._handle_page_up(MagicMock())
        self.assertEqual(content_control.selected_choice_index, 2)

    def test_handle_page_up_wrap_around(self) -> None:
        prompt = self._create_prompt()
        prompt._dimmension_max_height = 3

        content_control = MagicMock()
        content_control.selected_choice_index = 5
        content_control.choice_count = 10
        prompt.content_control = content_control

        def handle_up(event: Any) -> None:
            # simulate wrap-around behavior
            content_control.selected_choice_index = content_control.choice_count - 1

        prompt._handle_up = handle_up

        prompt._handle_page_up(MagicMock())
        self.assertEqual(content_control.selected_choice_index, content_control.choice_count - 1)

    def test_handle_page_up_at_top(self) -> None:
        prompt = self._create_prompt()
        prompt._handle_up = MagicMock()

        content_control = MagicMock()
        content_control.selected_choice_index = 0
        content_control.choice_count = 10
        prompt.content_control = content_control

        prompt._handle_page_up(MagicMock())
        self.assertEqual(content_control.selected_choice_index, 0)
        prompt._handle_up.assert_not_called()

    def test_handle_page_down(self) -> None:
        prompt = self._create_prompt()
        prompt._dimmension_max_height = 3

        content_control = MagicMock()
        content_control.selected_choice_index = 5
        content_control.choice_count = 10
        prompt.content_control = content_control

        def handle_down(event: Any) -> None:
            content_control.selected_choice_index += 1

        prompt._handle_down = handle_down

        prompt._handle_page_down(MagicMock())
        self.assertEqual(content_control.selected_choice_index, 8)

    def test_handle_page_down_wrap_around(self) -> None:
        prompt = self._create_prompt()
        prompt._dimmension_max_height = 3

        content_control = MagicMock()
        content_control.selected_choice_index = 5
        content_control.choice_count = 10
        prompt.content_control = content_control

        def handle_down(event: Any) -> None:
            # simulate wrap-around behavior
            content_control.selected_choice_index = 0

        prompt._handle_down = handle_down

        prompt._handle_page_down(MagicMock())
        self.assertEqual(content_control.selected_choice_index, 0)

    def test_handle_page_down_at_bottom(self) -> None:
        prompt = self._create_prompt()
        prompt._handle_down = MagicMock()

        content_control = MagicMock()
        content_control.selected_choice_index = 9
        content_control.choice_count = 10
        prompt.content_control = content_control

        prompt._handle_page_down(MagicMock())
        self.assertEqual(content_control.selected_choice_index, 9)
        prompt._handle_down.assert_not_called()

    def test_handle_home(self) -> None:
        assert browse_utils is not None
        prompt = self._create_prompt()

        content_control = MagicMock()
        content_control.choices = [
            {"value": browse_utils.Separator()},
            {"value": "first"},
            {"value": "second"},
        ]
        prompt.content_control = content_control

        prompt._handle_home(MagicMock())
        self.assertEqual(content_control.selected_choice_index, 1)

    def test_handle_end(self) -> None:
        assert browse_utils is not None
        prompt = self._create_prompt()

        content_control = MagicMock()
        content_control.choice_count = 3
        content_control.choices = [
            {"value": "first"},
            {"value": browse_utils.Separator()},
            {"value": "last"},
        ]
        prompt.content_control = content_control

        prompt._handle_end(MagicMock())
        self.assertEqual(content_control.selected_choice_index, 2)


if __name__ == "__main__":
    unittest.main()

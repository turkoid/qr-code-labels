import io
import secrets
import string
from pathlib import Path
from typing import NamedTuple
from typing import Self

import cairosvg
import drawsvg as svg
import segno
from pypdf import PdfWriter


class Dimensions2D(NamedTuple):
    width: float
    height: float

    def scale(self, factor: float) -> Self:
        return Dimensions2D(self.width * factor, self.height * factor)

    def resize(self, diff: float) -> Self:
        return Dimensions2D(self.width + diff, self.height + diff)

    def center(self, pt: tuple[float, float]) -> tuple[float, float]:
        x, y = pt
        return x - (self.width / 2), y - (self.height / 2)


# Q: don't worry about that little guy
ALPHANUM_UPPER = f"{string.ascii_uppercase}{string.digits}".replace("Q", "")
CODE_SIZE = 5

# sizes in inches
LETTER_DIM_IN = Dimensions2D(8.5, 11)
PAGE_MARGIN_IN = 0.5

# sizes in pixels
DPI = 300
PAGE_DIM = LETTER_DIM_IN.scale(DPI)
PAGE_MARGIN_PX = PAGE_MARGIN_IN * DPI
PAGE_WITHOUT_MARGINS_PX = PAGE_DIM.resize(-2 * PAGE_MARGIN_PX)

# qr
QR_QUIET_ZONE = 4
QR_MODULE_COUNT = segno.make("_" * CODE_SIZE, error="h").symbol_size()[0]
QR_CONTENT_MODULE_COUNT = QR_MODULE_COUNT - 2 * QR_QUIET_ZONE
QR_MODULE_SIZE = DPI / QR_MODULE_COUNT
QR_CONTENT_SIZE = QR_MODULE_SIZE * QR_CONTENT_MODULE_COUNT
BASE_LABEL_DIM = Dimensions2D(QR_CONTENT_SIZE / 3, QR_MODULE_SIZE * 3)

# font
QR_LABEL_FONT_FAMILY = "JetBrains Mono, monospace"
BASE_FONT_SIZE = 20


def generate_code() -> str:
    return "".join(secrets.choice(ALPHANUM_UPPER) for _ in range(CODE_SIZE))


class Generator:
    def __init__(
        self,
        *,
        num_codes: int,
        repeat: int = 1,
        scale: float = 1.5,
        output_dir: Path | None = None,
        name: str | None = None,
        include_cut_lines: bool = False,
        save_svgs: bool = False,
        save_codes: bool = False,
        group_codes: bool = False,
        fill_group: bool = False,
    ) -> None:
        self.num_codes = num_codes
        self.repeat = repeat
        self.scale = scale
        self.group_codes: bool = group_codes
        self.fill_group: bool = fill_group
        self.output_dir = output_dir or Path(".")
        self.name = "" if name is None else name.strip(" -_")
        self.save_svgs = save_svgs
        self.save_codes = save_codes
        self.include_cut_lines = include_cut_lines

        _name = self.name.replace(" ", "-")
        _name = f"{_name}_" if _name else ""
        self._base_filename = f"qr_codes_{_name}{self.scale}x{self.scale}"
        self._svg_output_dir = self.output_dir.joinpath("svgs")
        self._qr_size_px = self.scale * DPI
        self._canvas_dim: Dimensions2D | None = None
        self._grid_dim: Dimensions2D | None = None
        self._common_defs: dict[str, svg.DrawingElement] = {}
        self._pages: list[svg.Drawing] = []

        # remove old_files
        if self.save_svgs and self._svg_output_dir.exists():
            for file in self._svg_output_dir.glob(f"{self._base_filename}_p*.svg"):
                if file.is_file():
                    file.unlink()

    def generate_codes(self) -> list[str]:
        codes = {generate_code(): True for _ in range(self.num_codes)}
        # code collisions are unlikely, but this ensures uniqueness
        while len(codes) < self.num_codes:
            codes[generate_code()] = True
        return list(codes.keys())

    def _save_page(self, page_codes: list[list[svg.DrawingParentElement]]) -> None:
        if not page_codes:
            return

        page = svg.Drawing(
            *self._canvas_dim, origin=(0, 0), font_family=QR_LABEL_FONT_FAMILY
        )
        for svg_def in self._common_defs.values():
            page.append_def(svg_def)

        offset = 1 if self.include_cut_lines else 0
        for row, row_codes in enumerate(page_codes):
            for col, code in enumerate(row_codes):
                page.append(
                    svg.Use(
                        code,
                        col * self._qr_size_px + offset,
                        row * self._qr_size_px + offset,
                    )
                )
        # add cutout lines
        if self.include_cut_lines:
            h_line = self._common_defs["h_cut_line"]
            v_line = self._common_defs["v_cut_line"]
            for x in range(int(self._grid_dim.width + 1)):
                page.append(svg.Use(v_line, x * (self._qr_size_px + 1), 0))
            for y in range(int(self._grid_dim.height + 1)):
                page.append(svg.Use(h_line, 0, y * (self._qr_size_px + 1)))

        self._pages.append(page)

    def _write_codes_to_file(self, codes: list[str]) -> None:
        if not self.save_codes:
            return
        filename = f"{self._base_filename}_codes.txt"
        filepath = self.output_dir.joinpath(filename)
        filepath.parent.mkdir(parents=True, exist_ok=True)
        filepath.write_text("\n".join(codes))

    def _save_pdf(self, codes: list[str]) -> None:
        combined_pdf = PdfWriter()
        metadata = {
            "/Title": f"{self.name.title()} QR Labels",
            "/GeneratedCodes": "\n".join(codes),
        }
        combined_pdf.add_metadata(metadata)

        for page_index, page in enumerate(self._pages):
            svg_buf = io.StringIO()
            page.as_svg(svg_buf)
            if self.save_svgs:
                filename = f"{self._base_filename}_p{page_index}.svg"
                svg_file = self._svg_output_dir.joinpath(filename)
                svg_file.parent.mkdir(parents=True, exist_ok=True)
                svg_file.write_text(svg_buf.getvalue())
            svg_buf.seek(0)

            pdf_buf = io.BytesIO()
            cairosvg.svg2pdf(file_obj=svg_buf, write_to=pdf_buf)
            pdf_buf.seek(0)
            combined_pdf.append(pdf_buf)

        filename = f"{self._base_filename}.pdf"
        pdf_file = self.output_dir.joinpath(filename)
        pdf_file.parent.mkdir(parents=True, exist_ok=True)
        combined_pdf.write(pdf_file)

    def _calculate_grid_dim(self) -> Dimensions2D:
        qr_size = self._qr_size_px
        page_size = PAGE_WITHOUT_MARGINS_PX
        if self.include_cut_lines:
            qr_size += 1
            page_size = page_size.resize(-1)
        grid_dim = Dimensions2D(page_size.width // qr_size, page_size.height // qr_size)
        return grid_dim

    def _calculate_canvas_dim(self) -> Dimensions2D:
        if self.include_cut_lines:
            canvas_size = self._grid_dim.scale(self._qr_size_px + 1).resize(1)
        else:
            canvas_size = self._grid_dim.scale(self._qr_size_px)
        return canvas_size

    def create_labels(self) -> None:
        codes = self.generate_codes()

        # generate sizes
        self._qr_size_px = int(self.scale * DPI)
        self._grid_dim = self._calculate_grid_dim()
        self._canvas_dim = self._calculate_canvas_dim()
        center = self._qr_size_px / 2
        center_pt = (center, center)
        qr_label_dim = BASE_LABEL_DIM.scale(self.scale).resize(-1)
        font_size = int(BASE_FONT_SIZE * self.scale)

        # shared elements
        common_elements = []
        code_text_bg = svg.Rectangle(
            0, 0, *qr_label_dim, id="code_text_bg", fill="white", stroke="black"
        )
        common_elements.append(code_text_bg)
        if self.include_cut_lines:
            h_line = svg.Line(
                0,
                0,
                self._canvas_dim.width,
                0,
                id="h_cut_line",
                stroke="black",
                stroke_dasharray="1,5",
                stroke_width=1,
            )
            v_line = svg.Line(
                0,
                0,
                0,
                self._canvas_dim.height,
                id="v_cut_line",
                stroke="black",
                stroke_dasharray="1,5",
                stroke_width=1,
            )
            common_elements.append(h_line)
            common_elements.append(v_line)
        self._common_defs = {ele.id: ele for ele in common_elements}

        if self.group_codes and self.fill_group:
            _repeat = int(
                ((self.repeat - 1) / self._grid_dim.width + 1) * self._grid_dim.width
            )
        else:
            _repeat = self.repeat

        row = 0
        col = 0
        page_codes: list[list[svg.DrawingParentElement]] = []
        for code in codes:
            if self.group_codes and page_codes:
                row += 1
                col = 0
            # generate qr code
            qr = segno.make(code, error="h")
            svg_id = f"{code}_qr"
            qr_svg = qr.svg_inline(
                scale=self._qr_size_px / QR_MODULE_COUNT, svgid=svg_id
            )
            qr_code = svg.Raw(qr_svg)
            qr_code.id = svg_id

            # generate label
            code_text = svg.Text(
                code,
                font_size,
                center,
                center,
                center=True,
                text_anchor="middle",
                dominant_baseline="central",
                id=f"{code}_text",
            )

            qr_code_with_label = svg.Group(id=code)
            qr_code_with_label.append(svg.Use(qr_code, 0, 0))
            qr_code_with_label.append(
                svg.Use(code_text_bg, *qr_label_dim.center(center_pt))
            )
            qr_code_with_label.append(svg.Use(code_text, 0, 0))

            for _ in range(_repeat):
                if col == self._grid_dim.width:
                    row += 1
                    col = 0
                if row == self._grid_dim.height:
                    self._save_page(page_codes)
                    page_codes = []
                    row = 0
                if row == len(page_codes):
                    page_codes.append([])
                page_codes[row].append(qr_code_with_label)
                col += 1
        self._save_page(page_codes)
        self._write_codes_to_file(codes)
        self._save_pdf(codes)


if __name__ == "__main__":
    generator = Generator(
        num_codes=75,
        repeat=5,
        scale=1.5,
        output_dir=Path("qr_codes"),
        name="moving",
        group_codes=True,
        fill_group=True,
        include_cut_lines=True,
        save_svgs=True,
        save_codes=False,
    )
    generator.create_labels()

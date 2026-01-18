import io
import re
import secrets
import string
import sys
from pathlib import Path
from typing import NamedTuple
from typing import Self

import cairosvg
import click
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


# dimensions
DPI = 300
LETTER_DIM_IN = Dimensions2D(8.5, 11)
RENDER_SIZE = (f"{LETTER_DIM_IN.width}in", f"{LETTER_DIM_IN.height}in")
LETTER_DIM_PX = LETTER_DIM_IN.scale(DPI)
PAGE_MARGIN_IN = 0.5
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

# svg ids
CODE_TEXT_BG_ID = "code_text_bg"
H_CUT_LINE_ID = "h_line"
V_CUT_LINE_ID = "v_line"
CUT_LINES_ID = "cut_lines"


def generate_code() -> str:
    return "".join(secrets.choice(ALPHANUM_UPPER) for _ in range(CODE_SIZE))


class Generator:
    def __init__(
        self,
        *,
        count: int,
        repeat: int = 1,
        scale: float = 1.5,
        group_codes: bool = False,
        fill_group: bool = False,
        output_dir: Path | None = None,
        name: str | None = None,
        save_svgs: bool = False,
        save_codes: bool = False,
        include_cut_lines: bool = False,
    ) -> None:
        self.count = count
        self.repeat = repeat
        self.scale = scale
        self.group_codes: bool = group_codes
        self.fill_group: bool = fill_group
        self.output_dir = output_dir or Path(".")
        self.name = name.strip() if name else ""
        self.save_svgs = save_svgs
        self.save_codes = save_codes
        self.include_cut_lines = include_cut_lines

        if self.name:
            self._base_filename = f"{self.name}-qr-codes"
        else:
            self._base_filename = f"qr-codes-{self.scale:0.2f}in"
        self._qr_size_px = int(self.scale * DPI)
        self._qr_label_dim = BASE_LABEL_DIM.scale(self.scale).resize(-1)
        self._common_defs: dict[str, svg.DrawingElement] = {}
        self._pages: list[svg.Drawing] = []

        # calculated at generation
        self._canvas_dim: Dimensions2D | None = None
        self._grid_dim: Dimensions2D | None = None
        self._x_offset: int = 0
        self._y_offset: int = 0

    def generate_codes(self) -> list[str]:
        codes = {generate_code(): True for _ in range(self.count)}
        # code collisions are unlikely, but this ensures uniqueness
        while len(codes) < self.count:
            codes[generate_code()] = True
        return list(codes.keys())

    def _save_page(self, page_codes: list[list[svg.DrawingParentElement]]) -> None:
        if not page_codes:
            return

        page = svg.Drawing(*LETTER_DIM_PX, font_family=QR_LABEL_FONT_FAMILY)
        page.set_render_size(*RENDER_SIZE)
        for svg_def in self._common_defs.values():
            page.append_def(svg_def)

        qr_size = self._qr_size_px
        if self.include_cut_lines:
            qr_size += 1
        for y, row_codes in enumerate(page_codes):
            for x, code in enumerate(row_codes):
                page.append(
                    svg.Use(
                        code,
                        x * qr_size + self._x_offset,
                        y * qr_size + self._y_offset,
                    )
                )

        # add cut lines
        if self.include_cut_lines:
            cut_lines = self._common_defs[CUT_LINES_ID]
            page.append(svg.Use(cut_lines, 0, 0))

        self._pages.append(page)

    def _calculate_grid_dim(self) -> None:
        qr_size = self._qr_size_px
        page_size = PAGE_WITHOUT_MARGINS_PX
        if self.include_cut_lines:
            qr_size += 1
            page_size = page_size.resize(-1)
        grid_dim = Dimensions2D(page_size.width // qr_size, page_size.height // qr_size)
        self._grid_dim = grid_dim

    def _calculate_canvas_dim(self) -> None:
        if self.include_cut_lines:
            canvas_size = self._grid_dim.scale(self._qr_size_px + 1).resize(1)
        else:
            canvas_size = self._grid_dim.scale(self._qr_size_px)
        self._canvas_dim = canvas_size

    def _calculate_offsets(self) -> None:
        self._x_offset = int((LETTER_DIM_PX.width - self._canvas_dim.width) / 2)
        self._y_offset = int((LETTER_DIM_PX.height - self._canvas_dim.height) / 2)

    def _calculate_vars(self) -> None:
        self._calculate_grid_dim()
        self._calculate_canvas_dim()
        self._calculate_offsets()

    def _create_common_defs(self) -> None:
        common_elements = []

        # label background
        code_text_bg = svg.Rectangle(
            0, 0, *self._qr_label_dim, id=CODE_TEXT_BG_ID, fill="white", stroke="black"
        )
        common_elements.append(code_text_bg)

        # cut lines
        if self.include_cut_lines:
            h_line = svg.Line(
                0,
                0,
                PAGE_WITHOUT_MARGINS_PX.width,
                0,
                id=H_CUT_LINE_ID,
                stroke="black",
                stroke_dasharray="1,5",
                stroke_width=1,
            )
            v_line = svg.Line(
                0,
                0,
                0,
                PAGE_WITHOUT_MARGINS_PX.height,
                id=V_CUT_LINE_ID,
                stroke="black",
                stroke_dasharray="1,5",
                stroke_width=1,
            )

            cut_lines = svg.Group(id=CUT_LINES_ID)
            qr_size_with_line = self._qr_size_px + 1
            for x in range(int(self._grid_dim.width + 1)):
                cut_lines.append(
                    svg.Use(
                        v_line, x * qr_size_with_line + self._x_offset, PAGE_MARGIN_PX
                    )
                )
            for y in range(int(self._grid_dim.height + 1)):
                cut_lines.append(
                    svg.Use(
                        h_line, PAGE_MARGIN_PX, y * qr_size_with_line + self._y_offset
                    )
                )

            common_elements.append(h_line)
            common_elements.append(v_line)
            common_elements.append(cut_lines)

        self._common_defs = {ele.id: ele for ele in common_elements}

    def _save_pdf(self, codes: list[str]) -> None:
        click.echo(f"Output directory: {self.output_dir.absolute()}")
        if self.save_codes:
            filename = f"{self._base_filename}_codes.txt"
            codes_file = self.output_dir.joinpath(filename)
            codes_file.parent.mkdir(parents=True, exist_ok=True)
            codes_file.write_text("\n".join(codes))
            click.echo(f"Created ./{codes_file.as_posix()}")

        combined_pdf = PdfWriter()
        metadata = {
            "/Title": f"{self.name.title()} QR Labels",
            "/GeneratedCodes": "\n".join(codes),
        }
        combined_pdf.add_metadata(metadata)

        # remove old_files
        svg_output_dir = self.output_dir.joinpath("svgs")
        if self.save_svgs:
            svg_output_dir.mkdir(parents=True, exist_ok=True)
            svg_file_pattern = f"{self._base_filename}_p*.svg"
            click.echo(
                f"Cleaning old '{svg_file_pattern}' in ./{svg_output_dir.as_posix()}"
            )
            for file in svg_output_dir.glob(svg_file_pattern):
                if file.is_file():
                    file.unlink()

        for page_index, page in enumerate(self._pages):
            svg_buf = io.StringIO()
            page.as_svg(svg_buf)
            if self.save_svgs:
                filename = f"{self._base_filename}_p{page_index}.svg"
                svg_file = svg_output_dir.joinpath(filename)
                svg_file.write_text(svg_buf.getvalue())
            svg_buf.seek(0)

            pdf_buf = io.BytesIO()
            cairosvg.svg2pdf(file_obj=svg_buf, write_to=pdf_buf)
            pdf_buf.seek(0)
            combined_pdf.append(pdf_buf)

        if self.save_svgs:
            click.echo(
                f"Created {len(self._pages)} svg file(s) in ./{svg_output_dir.as_posix()}"
            )

        filename = f"{self._base_filename}.pdf"
        pdf_file = self.output_dir.joinpath(filename)
        pdf_file.parent.mkdir(parents=True, exist_ok=True)
        combined_pdf.write(pdf_file)

        click.echo(f"Created ./{pdf_file.as_posix()}")

    def create_labels(self) -> None:
        codes = self.generate_codes()

        # generate sizes
        self._qr_size_px = int(self.scale * DPI)
        self._calculate_vars()
        center = self._qr_size_px / 2
        center_pt = (center, center)
        font_size = int(BASE_FONT_SIZE * self.scale)

        self._create_common_defs()

        if self.group_codes and self.fill_group:
            width = int(self._grid_dim.width)
            _repeat = ((self.repeat - 1) // width + 1) * width
        else:
            _repeat = self.repeat

        click.echo(
            f"Generating {self.count}, {self.scale:0.2f}in QR codes, repeated {_repeat} times each"
        )
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
                svg.Use(
                    self._common_defs["code_text_bg"],
                    *self._qr_label_dim.center(center_pt),
                )
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

        self._save_pdf(codes)


@click.command()
@click.option(
    "-c",
    "--count",
    type=click.INT,
    default=1,
    help="Number of unique codes",
    show_default=True,
)
@click.option(
    "-r",
    "--repeat",
    type=click.INT,
    default=1,
    help="Number of copies",
    show_default=True,
)
@click.option(
    "-s",
    "--scale",
    type=click.FLOAT,
    default=1.5,
    help="Scale factor (base = 1 inch)",
    show_default=True,
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="Output directory",
)
@click.option(
    "-n",
    "--name",
    help="Name of the file(s) generated",
)
@click.option(
    "--grouped",
    is_flag=True,
    help="Group same codes. Useful if using cut lines",
)
@click.option(
    "--fill",
    is_flag=True,
    help="If grouped, repeat codes until row is filled",
)
@click.option(
    "--include-cut-lines",
    is_flag=True,
    help="Draw dotted lines for cutting",
)
@click.option(
    "--save-svgs",
    is_flag=True,
    help="Writes svg files generated to 'svgs' directory relative to '--output' directory",
)
@click.option(
    "--save-codes",
    is_flag=True,
    help="Writes the generated codes to a text file relative '--output' directory",
)
@click.argument(
    "spec",
    default=None,
)
def cli(
    count: int,
    repeat: int,
    scale: float,
    grouped: bool,
    fill: bool,
    output: Path | None,
    name: str | None,
    save_svgs: bool,
    save_codes: bool,
    include_cut_lines: bool,
    spec: str | None,
) -> None:
    """
    Generate QR Codes using a 5-character code (uppercase, alphanumeric, excluding 'Q')

    Tile it and save it to a PDF file to be printed on LETTER sized paper

    SPEC is an optional format spec that is {count}[x{repeat}][@{scale}]. This takes precedent over options
    """
    try:
        if spec:
            match = re.match(r"^\s*(\d+)(?:x(\d+))?(?:@(\d+(?:\.?\d+)?))?\s*$", spec)
            if not match:
                raise ValueError("SPEC is invalid")
            _count, _repeat, _scale = match.groups()
            count = count if _count is None else int(_count)
            repeat = repeat if _repeat is None else int(_repeat)
            scale = scale if _scale is None else float(_scale)

        if count < 1:
            raise ValueError(f"Invalid value for 'count': {count} is not >=1")
        if repeat < 1:
            raise ValueError(f"Invalid value for 'repeat': {repeat} is not >=1")
        if scale < 1.0:
            raise ValueError(f"Invalid value for 'scale': {scale} is not >=1.0")

        generator = Generator(
            count=count,
            repeat=repeat,
            scale=scale,
            group_codes=grouped,
            fill_group=fill,
            output_dir=output,
            name=name,
            save_svgs=save_svgs,
            save_codes=save_codes,
            include_cut_lines=include_cut_lines,
        )
        generator.create_labels()
    except ValueError as ex:
        click.echo(f"ERROR: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    cli()

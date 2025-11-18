"""CLI wrapper for generate_models command."""

from __future__ import annotations

import sys

import click

try:
    import frappe
    from frappe.commands import get_site, pass_context
except ImportError:
    frappe = None  # type: ignore
    pass_context = lambda f: f  # type: ignore
    get_site = lambda ctx, **kw: None  # type: ignore

from .generate_models import generate_docmodels


def generate_models_command(
    doctypes: list[str],
    *,
    with_children: bool = True,
    with_links: bool = True,
) -> None:
    """CLI command to generate DocModel classes and print to stdout.

    Args:
        doctypes: List of DocType names to generate models for
        with_children: Whether to include child table models
        with_links: Whether to infer Meta.links from fetch_from fields
    """
    try:
        code = generate_docmodels(doctypes, with_children=with_children, with_links=with_links)
        print(code)
    except ImportError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


# Click command group for bench integration
@click.group("powertools")
def powertools_group():
    """Frappe Powertools commands."""
    pass


@powertools_group.command("gen-model")
@pass_context
@click.argument("doctypes", nargs=-1, required=True)
@click.option(
    "--with-children/--no-children",
    default=True,
    help="Include child table models (default: True)",
)
@click.option(
    "--with-links/--no-links",
    default=True,
    help="Infer Meta.links from fetch_from fields (default: True)",
)
def gen_model_cli(
    context, doctypes: tuple[str, ...], with_children: bool, with_links: bool
) -> None:
    """Generate DocModel classes for the given DocTypes.

    Examples:\n
        bench powertools gen-model "Sponsor Contract"\n
        bench powertools gen-model "Sponsor Contract" "Person Sponsorship"\n
        bench powertools gen-model "Receipt" --no-children\n
    """
    if frappe is None:
        click.secho("Error: Frappe is required for this command", fg="red")
        sys.exit(1)

    # Initialize Frappe with the site from context
    site = get_site(context)
    frappe.init(site=site)
    frappe.connect()

    try:
        generate_models_command(
            doctypes=list(doctypes),
            with_children=with_children,
            with_links=with_links,
        )
    finally:
        frappe.destroy()

import argparse
import json
import shutil
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import frontmatter
import sass
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from loguru import logger
from marko.html_renderer import HTMLRenderer
from marko.inline import Image
from marko.parser import Parser

load_dotenv()

current_dir = Path(__file__).resolve().parent

src_dir = current_dir.joinpath("src")
assets_dir = src_dir.joinpath("assets")
assets_css_dir = assets_dir.joinpath("css")
assets_images_dir = assets_dir.joinpath("images")
assets_js_dir = assets_dir.joinpath("js")
posts_dir = src_dir.joinpath("posts")
templates_dir = src_dir.joinpath("templates")

dist_dir = current_dir.joinpath("dist")
dist_assets_dir = dist_dir.joinpath("assets")
dist_assets_css_dir = dist_assets_dir.joinpath("css")
dist_assets_images_dir = dist_assets_dir.joinpath("images")
dist_assets_js_dir = dist_assets_dir.joinpath("js")
dist_assets_data_dir = dist_assets_dir.joinpath("data")
dist_posts_dir = dist_dir.joinpath("posts")

cf_page_proj = "chad-site"

featured_post_slugs = ["01-welcome-to-site"]

jj2_env = Environment(loader=FileSystemLoader(templates_dir))


class NoGivenTemplateException(Exception):
    pass


@contextmanager
def ensure_dir_and_open_file(path):
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        yield file


def build_page(dest_path, template_path=None, template=None, context=None):
    if not template_path and not template:
        raise NoGivenTemplateException()
    if template_path:
        template = jj2_env.get_template(template_path)
    with ensure_dir_and_open_file(dest_path) as file:
        rendered = template.render() if context is None else template.render(context)
        file.write(rendered)


def walk_ast(ctx, element):
    if isinstance(element, Image):
        alt = element.children[0].children
        url = element.dest
        title = element.title
        ctx["images"].append(
            {"url": url, "alt": alt, "title": title, "page_url": ctx["page_url"]}
        )
    if hasattr(element, "children"):
        for child in element.children:
            walk_ast(ctx, child)


class MyHTMLRenderer(HTMLRenderer):
    def render_image(self, element):
        alt = self.render_children(element)
        src = element.dest
        title = element.title
        img_html = f'<img src="{src}" alt="{alt}">'
        if title:
            return f"<figure>{img_html}<figcaption>{title}</figcaption></figure>"
        return img_html


def build(args):
    base_context = {"current_year": datetime.now().year}

    parser = Parser()
    renderer = MyHTMLRenderer()
    post_tpl = jj2_env.get_template("post.html")
    posts = []
    posts_map = {}
    images = []
    for file in posts_dir.iterdir():
        post = frontmatter.load(file)
        if post["draft"]:
            continue
        slug = post["slug"]
        order = None
        try:
            split = slug.split("-")
            assert len(split) > 0
            order = int(split[0])
        except Exception as e:
            logger.error(e)
            continue
        post["order"] = order
        dist_post_dir = dist_posts_dir.joinpath(slug)
        ast = parser.parse(post.content)
        walk_ast_ctx = {"page_url": f"/posts/{slug}", "images": []}
        walk_ast(walk_ast_ctx, ast)
        images.extend(walk_ast_ctx["images"])
        html = renderer.render(ast)
        abstract = " ".join(post.content.split())
        if "description" in post:
            abstract = post["description"]
        post["abstract"] = abstract
        post["date_fmt"] = post["date"].strftime("%b %d, %Y")
        build_page(
            dist_post_dir.joinpath("index.html"),
            template=post_tpl,
            context={
                **base_context,
                **post,
                "post_html": html,
                "page_title": post["title"],
            },
        )
        posts.append(post)
        posts_map[slug] = post

    sorted_posts = sorted(posts, key=lambda p: (-p["order"], -p["date"].toordinal()))

    build_page(
        dist_posts_dir.joinpath("index.html"),
        template_path="posts.html",
        context={**base_context, "posts": sorted_posts},
    )

    featured_posts = [posts_map[slug] for slug in featured_post_slugs]

    build_page(
        dist_dir.joinpath("index.html"),
        template_path="index.html",
        context={**base_context, "featured_posts": featured_posts},
    )

    build_page(
        dist_dir.joinpath("404.html"),
        template_path="404.html",
    )

    with ensure_dir_and_open_file(dist_assets_data_dir.joinpath("images.json")) as file:
        file.write(json.dumps(images))

    sass.compile(dirname=(assets_css_dir, dist_assets_css_dir))
    shutil.copytree(assets_images_dir, dist_assets_images_dir, dirs_exist_ok=True)
    shutil.copytree(assets_js_dir, dist_assets_js_dir, dirs_exist_ok=True)


def deploy(args):
    if not dist_dir.is_dir():
        logger.error("dist directory does not exist, run build first.")
        return
    if shutil.which("wrangler") is not None:
        logger.info("wrangler found, using it.")
        try:
            cmd = [
                "wrangler",
                "pages",
                "deploy",
                dist_dir,
                f"--project-name={cf_page_proj}",
                "--commit-dirty=true",
            ]
            result = subprocess.run(cmd, check=True)
            logger.info(
                "wrangler deploy complete with returncode {}.", result.returncode
            )
            return result.returncode
        except subprocess.CalledProcessError as e:
            return e.returncode
    else:
        logger.info("wrangler not found, falling back to cloudflare SDK deploy.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    build_parser = subparsers.add_parser("build")
    build_parser.set_defaults(func=build)

    deploy_parser = subparsers.add_parser("deploy")
    deploy_parser.set_defaults(func=deploy)

    args = parser.parse_args()
    args.func(args)

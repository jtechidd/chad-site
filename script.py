import argparse
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import frontmatter
import mistune
import sass
from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader
from loguru import logger

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
dist_posts_dir = dist_dir.joinpath("posts")

cf_page_proj = "chad-site"


def build(args):
    base_context = {"current_year": datetime.now().year}
    dist_dir.mkdir(parents=True, exist_ok=True)
    jj2_env = Environment(loader=FileSystemLoader(templates_dir))
    index_tpl = jj2_env.get_template("index.html")
    with open(
        dist_dir.joinpath("index.html"), mode="w", encoding="utf-8"
    ) as index_html:
        index_html.write(index_tpl.render(base_context))

    dist_posts_dir.mkdir(parents=True, exist_ok=True)
    markdown = mistune.create_markdown()
    post_tpl = jj2_env.get_template("post.html")
    posts = []
    for file in posts_dir.iterdir():
        post = frontmatter.load(file)
        slug = post["slug"]
        dist_post_dir = dist_posts_dir.joinpath(slug)
        dist_post_dir.mkdir(parents=True, exist_ok=True)
        html = markdown(post.content)
        abstract = " ".join(post.content.split())
        if "description" in post:
            abstract = post["description"]
        post["abstract"] = abstract
        post["date_fmt"] = post["date"].strftime("%b %d, %Y")
        with open(
            dist_post_dir.joinpath("index.html"),
            mode="w",
            encoding="utf-8",
        ) as post_html:
            context = {
                **base_context,
                **post,
                "post_html": html,
                "page_title": post["title"],
            }
            post_html.write(post_tpl.render(context))
        posts.append(post)

    posts_tpl = jj2_env.get_template("posts.html")
    with open(
        dist_posts_dir.joinpath("index.html"), mode="w", encoding="utf-8"
    ) as posts_html:
        context = {**base_context, "posts": posts}
        posts_html.write(posts_tpl.render(context))

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

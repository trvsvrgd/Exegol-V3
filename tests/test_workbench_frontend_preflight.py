import json

from scripts import workbench_frontend_preflight


def write_package(workbench, package, version):
    package_dir = workbench / "node_modules" / package
    package_dir.mkdir(parents=True)
    package_dir.joinpath("package.json").write_text(json.dumps({"version": version}), encoding="utf-8")


def create_frontend_install(tmp_path):
    workbench = tmp_path / "workbench_ui"
    workbench.mkdir()
    workbench.joinpath("package.json").write_text(json.dumps({"private": True}), encoding="utf-8")
    workbench.joinpath("package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/next": {"version": "16.2.4"},
                    "node_modules/react": {"version": "19.2.4"},
                    "node_modules/react-dom": {"version": "19.2.4"},
                }
            }
        ),
        encoding="utf-8",
    )
    write_package(workbench, "next", "16.2.4")
    write_package(workbench, "react", "19.2.4")
    write_package(workbench, "react-dom", "19.2.4")
    workbench.joinpath("node_modules/next/dist/client/components/builtin").mkdir(parents=True)
    workbench.joinpath("node_modules/next/dist/client/components/builtin/global-error.js").write_text(
        "module.exports = {}",
        encoding="utf-8",
    )
    return workbench


def test_validate_frontend_install_accepts_matching_node_modules(tmp_path):
    workbench = create_frontend_install(tmp_path)

    assert workbench_frontend_preflight.validate_frontend_install(workbench) == []


def test_validate_frontend_install_reports_version_mismatch(tmp_path):
    workbench = create_frontend_install(tmp_path)
    workbench.joinpath("node_modules/next/package.json").write_text(
        json.dumps({"version": "16.0.0"}),
        encoding="utf-8",
    )

    findings = workbench_frontend_preflight.validate_frontend_install(workbench)

    assert findings == [
        "node_modules/next is 16.0.0, expected 16.2.4; run npm install in workbench_ui"
    ]


def test_repair_next_cache_removes_only_development_cache(tmp_path):
    workbench = create_frontend_install(tmp_path)
    workbench.joinpath(".next/dev/server").mkdir(parents=True)
    workbench.joinpath(".next/server").mkdir(parents=True)

    removed = workbench_frontend_preflight.repair_next_cache(workbench, "development")

    assert removed == [workbench.joinpath(".next/dev").resolve()]
    assert not workbench.joinpath(".next/dev").exists()
    assert workbench.joinpath(".next/server").exists()


def test_repair_next_cache_removes_production_output(tmp_path):
    workbench = create_frontend_install(tmp_path)
    workbench.joinpath(".next/server").mkdir(parents=True)

    removed = workbench_frontend_preflight.repair_next_cache(workbench, "production")

    assert removed == [workbench.joinpath(".next").resolve()]
    assert not workbench.joinpath(".next").exists()

# ocp_install_workspace

## install_tool

### Architecture
![alt text](<image/ocp install python app architecture.png>)

### Version Info
* using uv 
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
* using python 3.12
```bash
uv venv --python 3.12
```

### How to start
1. install streamlit package
```
uv pip install streamlit
```
```
uv pip install yamlgen
```
2. execute python
```
cd install_tool
```
```bash
streamlit run prep_app.py
```

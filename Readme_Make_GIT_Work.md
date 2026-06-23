# Make GIT Work 

git config --global http.sslBackend schannel
```
11. Test the connection
```bash
ssh -T git@github.com
```
12. Go to your python virtual environment to use system certificates
```bash
pip install python-certifi-win32


# Start backend

```
pip install  -r requirements-dev.txt
python -m backend.seed 
```

# Start the App  
## Start Uvicorn site - REST Server
```
uvicorn backend.main:app --reload
```

##Start the front end
Open a new terminal tab
```
cd .\frontend\
npm install 
npm run dev 
```
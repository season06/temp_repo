repo tag: `v3.30.0.rc8`

- fix ui error
```
> debug with ui :  S7016: Could not find a declaration file for module 'react'. '/usr/src/app/node_modules/react/index.js' 
  implicitly has an 'any' type.                                                                                                   
    Try `npm i --save-dev @types/react` if it exists or add a new declaration (.d.ts) file containing `declare module 'react';`
```

`package.json`
```
  "devDependencies": {
    "@types/react": "^18.0.0",
    "@types/react-dom": "^18.0.0",
  }
````

- fix cve
`dependencies.gradle`
```
revSpringAI = '1.1.4'
```

- build
```
docker build -f docker/server/Dockerfile -t conductor:v3.30.0.rc8
```

- push
```
docker tag conductor:v3.30.0.rc8 season1006/conductor:v3.30.0.rc8
docker push season1006/conductor:v3.30.0.rc8
```
To repro:

`just restore < trouble-2025-04-01T18:28:24+0000-sql`
`just runme`

Log in as Bob

Go to <http://localhost:9000/serialized/hand/1/>

You'll see
```
PlayerException at /serialized/hand/1/
bob is not seated, so cannot be converted to a bridge-library Player
```

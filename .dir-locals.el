(
 (python-mode
  .
  (
   (lsp-pylsp-server-command . ("poetry" "run" "pylsp"))
   (eval . (add-to-list 'exec-path (concat (file-name-as-directory (car (process-lines "poetry" "env" "info" "--path"))) "bin")))
   ))
 )

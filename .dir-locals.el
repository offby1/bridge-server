(

 (nil
  .
  (
   (lsp-pylsp-server-command . ("uv" "run" "pylsp"))
   (eval . (ignore-errors
             (add-to-list 'exec-path (file-name-parent-directory (concat (car (process-lines "uv" "python" "find")))))))
   ))
 (python-base-mode
  . ((eglot-workspace-configuration
      . (:python (:pythonPath ".venv/bin/python")
                 :python.analysis (:typeCheckingMode "basic"
                                                     :diagnosticMode "workspace")))))
 )

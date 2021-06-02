syn clear
syn match Error   /#*/
syn match Error   /#\d\+R.*/
syn match Comment /##.*/
syn match Special /#\d\+[A-QS-Z]/
syn match Special /#\d\+R[^#]*#/
syn match Operator /^\t.*/ contains=ALL contains=@Spell
syn match Error /\S\@<=[ 	　]\+$/
set commentstring=##\ %s

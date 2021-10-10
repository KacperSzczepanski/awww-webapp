# Mips convention: use $a0-$a3 then store additional parameters in stack directly above $sp
# a0 is R1
# a1 is G1
# a2 is B1
# a3 is R2
# M[$sp] is G2
# M[$sp+4] is B2

.text
main:	
	#test case
	addi $a0, $0, 15	#R1
	addi $a1, $0, 20	#G1
	addi $a2, $0, 25	#B1
	addi $a3, $0, 25	#R2
	addi $t0, $0, 20	#G2
	addi $t1, $0, 15	#B2
	addi $sp, $sp, -8
	sw $t0, 0($sp)
	sw $t1, 4($sp)
	jal abs_diff_color
	
	end:
		j end
		
		
# calculates the difference in each color R,G,B seperately and adds it to the return value
abs_diff_color:
	
	#calc abs diff of R1,R2 in $t3 and add to $v0
	sub $t1, $a0, $a3
	sra $t2,$t1,31   
	xor $t1,$t1,$t2    
	sub $t3,$t1,$t2
	add $v0, $0, $t3 
	
	#calc abs diff of G1,G2 in $t3 and add to $v0
	lw $t0, 0($sp)	#load G2 from memory
	sub $t1, $a1, $t0
	sra $t2,$t1,31   
	xor $t1,$t1,$t2   
	sub $t3,$t1,$t2
	add $v0, $v0, $t3  
	
	#calc abs diff of B1,B2 in $t3 and add to $v0
	lw $t0, 4($sp)	#load B2 from memory
	sub $t1, $a2, $t0
	sra $t2,$t1,31   
	xor $t1,$t1,$t2   
	sub $t3,$t1,$t2
	add $v0, $v0, $t3
	
	jr $ra